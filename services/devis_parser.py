import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import fitz
from PIL import Image

from services.ocr_windows import OcrNotAvailableError, ocr_image


AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})")
SRX_RE = re.compile(r"SRX(?P<yymm>\d{4})(?P<type>[A-Z]{3})(?P<num>\d{6})")
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+33|0)\s?\d(?:[\s.-]?\d{2}){4}\b")
CP_VILLE_RE = re.compile(r"\b(\d{5})\s+(.+)")
NOISE_HEADER_RE = re.compile(
    r"\b(r[eé]alis[eé]\s+par|date\s+du\s+devis|r[eé]f\s+affaire|devis|facture|bon de commande)\b",
    re.IGNORECASE,
)
STREET_HINT_RE = re.compile(
    r"\b(rue|allee|all[ée]e|avenue|av\.?|bd|boulevard|chemin|route|impasse|zac|za)\b",
    re.IGNORECASE,
)
LEGAL_NOISE_RE = re.compile(
    r"\b(sas|sarl|rcs|r\.c\.s|naf|siret|capital|eur|au capital)\b|b\s?\d+",
    re.IGNORECASE,
)
TEL_MARKER_RE = re.compile(r"\b(t[eé]l|tel|fax)\b", re.IGNORECASE)
CLIENT_STOP_RE = re.compile(
    r"\b(contact commercial|t[eé]l|tel|fax|validit[eé]|d[eé]signation|désignation|conditions)\b",
    re.IGNORECASE,
)
ESSENCE_RE = re.compile(
    r"\b(ch[eê]ne|h[eê]tre|fr[eê]ne|sapin|pin|hêtre|chêne)\b", re.IGNORECASE
)


class DevisParser:
    def __init__(self, debug: bool = False):
        self.debug = debug
        self._debug_cache: dict[Path, dict] = {}

    def _clean_line(self, value: str) -> str:
        value = re.sub(r"[^\wÀ-ÖØ-öø-ÿ&'()/\-\., ]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _is_probable_company_name(self, value: str) -> bool:
        if not value:
            return False
        cleaned = self._clean_line(value)
        lowered = cleaned.lower()
        if "vaugarny" in lowered:
            return False
        if CP_VILLE_RE.search(cleaned):
            return False
        if ":" in cleaned:
            return False
        if NOISE_HEADER_RE.search(lowered):
            return False
        if not (3 <= len(cleaned) <= 60):
            return False
        allowed_chars = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ&\-/ ]", cleaned)
        if not allowed_chars:
            return False
        if (len(allowed_chars) / max(len(cleaned), 1)) < 0.7:
            return False
        return True

    def _dump_lines_around(self, lines: list[str], index: int, radius: int = 7) -> str:
        if index is None:
            return ""
        start = max(index - radius, 0)
        end = min(index + radius + 1, len(lines))
        snippet = [f"{idx}:{lines[idx]}" for idx in range(start, end)]
        return "\n".join(snippet)

    def parse(self, path: Path) -> dict:
        text, lines, blocks = self._extract_text(path)
        warnings = []
        if not lines:
            warnings.append("Texte du devis illisible ou vide.")

        fourniture_ht = self._find_amount_by_label(
            lines, r"PRIX DE LA FOURNITURE HT\s*:\s*([\d\s]+,\d{2})"
        )
        prestations_ht = self._find_amount_by_label(
            lines, r"PRIX PRESTATIONS ET SERVICES HT\s*:\s*([\d\s]+,\d{2})"
        )
        total_ht = self._find_amount_by_label(
            lines, r"TOTAL HORS TAXE\s*:\s*([\d\s]+,\d{2})"
        )
        if not prestations_ht:
            services_ht = self._find_amount_by_label(
                lines, r"PRIX.*SERVICES.*HT\s*:\s*([\d\s]+,\d{2})"
            )
            eco_ht = self._find_amount_by_label(
                lines, r"PRIX.*ECO.*HT\s*:\s*([\d\s]+,\d{2})"
            )
            prestations_ht = self._sum_amounts([services_ht, eco_ht])
            if prestations_ht and not fourniture_ht:
                warnings.append(
                    "Fourniture absente: prestations calculées depuis SERVICES/ECO."
                )

        devis_match = self._find_devis_reference(lines)
        devis_annee_mois = devis_match[0] if devis_match else ""
        devis_num = devis_match[1] if devis_match else ""
        devis_type = devis_match[2] if devis_match else ""

        ref_affaire = self._find_ref_affaire(lines)
        client_details = self._find_client_details(lines, blocks)
        commercial_details = self._find_commercial_details(lines, blocks)
        ocr_snapshots = []
        ocr_used = False
        if self._is_invalid_client_name(client_details["nom"]) or self._is_invalid_commercial_name(
            commercial_details["nom"]
        ):
            ocr_results = self._run_ocr_fallback(path, blocks, warnings)
            ocr_snapshots.extend(ocr_results)
            ocr_text = "\n".join(result["text"] for result in ocr_results if result["text"])
            ocr_lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
            if ocr_lines:
                ocr_client = self._find_client_details(ocr_lines, None)
                ocr_commercial = self._find_commercial_details(ocr_lines, None)
                if self._is_invalid_client_name(client_details["nom"]) and not self._is_invalid_client_name(
                    ocr_client["nom"]
                ):
                    client_details = ocr_client
                    ocr_used = True
                if self._is_invalid_commercial_name(
                    commercial_details["nom"]
                ) and not self._is_invalid_commercial_name(ocr_commercial["nom"]):
                    commercial_details = ocr_commercial
                    ocr_used = True
        srx_debug = self.debug and "SRX2511AFF037501" in text.replace(" ", "")
        if "réalisé par" in client_details["nom"].lower():
            dump = self._dump_lines_around(lines, client_details.get("code_index"))
            warnings.append(
                "Client: nom contient 'Réalisé par'.\n"
                f"[PARSE] context around Code client:\n{dump}"
            )
        if self.debug and self._is_invalid_client_name(client_details["nom"]):
            dump = self._dump_lines_around(lines, client_details.get("code_index"))
            warnings.append(
                "[DEBUG] Détection client incohérente.\n"
                f"[PARSE] context around Code client:\n{dump}"
            )
        if CP_VILLE_RE.search(commercial_details["nom"]):
            dump = self._dump_lines_around(lines, commercial_details.get("contact_index"))
            warnings.append(
                "Commercial: nom ressemble à un CP/Ville.\n"
                f"[PARSE] context around contact commercial:\n{dump}"
            )
        if self.debug and self._is_invalid_commercial_name(commercial_details["nom"]):
            dump = self._dump_lines_around(lines, commercial_details.get("contact_index"))
            warnings.append(
                "[DEBUG] Détection commercial incohérente.\n"
                f"[PARSE] context around contact commercial:\n{dump}"
            )
        if srx_debug:
            if "réalisé par" in client_details["nom"].lower():
                warnings.append("Client SRX: nom contient 'Réalisé par'.")
            if CP_VILLE_RE.search(commercial_details["nom"]):
                warnings.append("Client SRX: nom commercial ressemble à un CP/Ville.")
        source = "OCR" if ocr_used else "TEXT"
        warnings.append(
            f"DEBUG source={source} client_nom={client_details['nom']} "
            f"commercial_nom={commercial_details['nom']}"
        )
        if ocr_used and ocr_snapshots:
            excerpt = " | ".join(
                snapshot["text"][:160].replace("\n", " ")
                for snapshot in ocr_snapshots
                if snapshot.get("text")
            )
            if excerpt:
                warnings.append(f"OCR extrait: {excerpt}")
        if not devis_num:
            warnings.append("Devis SRX introuvable.")
        if not ref_affaire:
            warnings.append("Réf affaire introuvable.")
        if not client_details["nom"]:
            warnings.append("Client introuvable (ancre 'Code client :').")
        esc_gamme = self._find_modele(lines)
        finitions = self._extract_finitions(lines)
        esc_finition_marches = finitions.get("marche", "")
        esc_finition_structure = finitions.get("structure", "")
        esc_finition_mains_courante = finitions.get("main_courante", "")
        esc_finition_contremarche = finitions.get("contremarche", "")
        esc_finition_rampe = finitions.get("rampe", "")
        esc_main_courante, esc_main_courante_scellement = self._find_main_courante(lines)
        esc_nez_de_marches = self._find_nez_de_marches(lines)
        esc_essence = self._extract_essence(
            [
                esc_finition_marches,
                esc_finition_structure,
                esc_finition_mains_courante,
                esc_finition_contremarche,
                esc_finition_rampe,
            ]
        )
        esc_tete_de_poteau = self._find_tete_poteau(lines)
        esc_poteaux_depart = self._find_poteaux_depart(lines)
        pose_sold, pose_amount = self._find_pose_details(lines)

        data = {
            "lines": lines,
            "fourniture_ht": fourniture_ht,
            "prestations_ht": prestations_ht,
            "total_ht": total_ht,
            "devis_annee_mois": devis_annee_mois,
            "devis_num": devis_num,
            "devis_type": devis_type,
            "ref_affaire": ref_affaire,
            "client_nom": client_details["nom"],
            "client_adresse1": client_details["adresse1"],
            "client_adresse2": client_details["adresse2"],
            "client_cp": client_details["cp"],
            "client_ville": client_details["ville"],
            "client_tel": client_details["tel"],
            "client_email": client_details["email"],
            "client_contact": client_details["contact"],
            "commercial_nom": commercial_details["nom"],
            "commercial_tel": commercial_details["tel"],
            "commercial_email": commercial_details["email"],
            "esc_gamme": esc_gamme,
            "esc_finition_marches": esc_finition_marches,
            "esc_finition_structure": esc_finition_structure,
            "esc_finition_mains_courante": esc_finition_mains_courante,
            "esc_finition_contremarche": esc_finition_contremarche,
            "esc_finition_rampe": esc_finition_rampe,
            "esc_essence": esc_essence,
            "esc_main_courante": esc_main_courante,
            "esc_main_courante_scellement": esc_main_courante_scellement,
            "esc_nez_de_marches": esc_nez_de_marches,
            "esc_tete_de_poteau": esc_tete_de_poteau,
            "esc_poteaux_depart": esc_poteaux_depart,
            "pose_sold": pose_sold,
            "pose_amount": pose_amount,
            "parse_warning": " ".join(warnings).strip(),
        }
        if self.debug:
            data["debug"] = [
                f"[PARSE] client_nom={client_details['nom']}",
                f"[PARSE] client_cp_ville={client_details['cp']} {client_details['ville']}".strip(),
                f"[PARSE] commercial_nom={commercial_details['nom']}",
                f"devis_annee_mois={devis_annee_mois}",
                f"devis_type={devis_type}",
                f"devis_num={devis_num}",
                f"ref_affaire={ref_affaire}",
                f"client_nom={client_details['nom']}",
                f"client_adresse1={client_details['adresse1']}",
                f"client_adresse2={client_details['adresse2']}",
                f"client_cp={client_details['cp']}",
                f"client_ville={client_details['ville']}",
                f"client_tel={client_details['tel']}",
                f"client_email={client_details['email']}",
                f"client_contact={client_details['contact']}",
                f"commercial_nom={commercial_details['nom']}",
                f"commercial_tel={commercial_details['tel']}",
                f"commercial_email={commercial_details['email']}",
                f"fourniture_ht={fourniture_ht}",
                f"prestations_ht={prestations_ht}",
                f"total_ht={total_ht}",
                f"pose_sold={pose_sold}",
                f"pose_amount={pose_amount}",
                f"esc_gamme={esc_gamme}",
                f"esc_finition_marches={esc_finition_marches}",
                f"esc_finition_structure={esc_finition_structure}",
                f"esc_finition_mains_courante={esc_finition_mains_courante}",
                f"esc_finition_contremarche={esc_finition_contremarche}",
                f"esc_finition_rampe={esc_finition_rampe}",
                f"esc_essence={esc_essence}",
                f"esc_main_courante={esc_main_courante}",
                f"esc_main_courante_scellement={esc_main_courante_scellement}",
                f"esc_nez_de_marches={esc_nez_de_marches}",
                f"esc_tete_de_poteau={esc_tete_de_poteau}",
                f"esc_poteaux_depart={esc_poteaux_depart}",
            ]
            if srx_debug:
                data["debug"].extend(
                    [
                        f"srx_client_nom={client_details['nom']}",
                        f"srx_client_cp_ville={client_details['cp']} {client_details['ville']}",
                        f"srx_commercial_nom={commercial_details['nom']}",
                    ]
                )
            self._run_internal_debug_test(path, data, warnings)
        self._debug_cache[path] = {
            "lines": lines,
            "blocks": blocks,
            "ocr": ocr_snapshots,
        }
        return data

    def _extract_text(self, path: Path) -> tuple[str, list[str], list[dict]]:
        if not path.exists():
            raise FileNotFoundError(path)
        text_parts = []
        blocks = []
        with fitz.open(path) as doc:
            for page_index, page in enumerate(doc):
                page_blocks = page.get_text("blocks") or []
                page_blocks = sorted(page_blocks, key=lambda block: (block[1], block[0]))
                for block in page_blocks:
                    text = (block[4] or "").strip()
                    if not text:
                        continue
                    bbox = (block[0], block[1], block[2], block[3])
                    blocks.append(
                        {"text": text, "bbox": bbox, "page_index": page_index}
                    )
                    text_parts.append(text)
        text = "\n".join(text_parts)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return text, lines, blocks

    def _find_amount_by_label(self, lines, pattern):
        regex = re.compile(pattern, re.IGNORECASE)
        for line in lines:
            match = regex.search(line)
            if match:
                return self._normalize_amount(match.group(1))
        return ""

    def _extract_amount(self, text):
        match = AMOUNT_RE.search(text)
        if not match:
            return ""
        return self._normalize_amount(match.group(1))

    def _sum_amounts(self, amounts: list[str]) -> str:
        values = [amount for amount in amounts if amount]
        if not values:
            return ""
        total = Decimal("0")
        for value in values:
            normalized = value.replace(" ", "").replace("\u202f", "").replace(",", ".")
            try:
                total += Decimal(normalized)
            except InvalidOperation:
                continue
        return self._normalize_amount(f"{total:.2f}")

    def _normalize_amount(self, value: str) -> str:
        value = value.replace("\u202f", " ")
        value = re.sub(r"\s+", " ", value).strip()
        if "," in value and "." in value:
            value = value.replace(".", "")
        if "." in value:
            value = value.replace(".", ",")
        return value

    def _find_devis_reference(self, lines):
        for line in lines:
            if "DEVIS" not in line.upper():
                continue
            match = SRX_RE.search(line.replace(" ", ""))
            if match:
                yymm = match.group("yymm")
                num = match.group("num")
                return yymm, num, match.group("type")
        return None

    def _find_ref_affaire(self, lines):
        for idx, line in enumerate(lines):
            if line.strip().lower().startswith("réf affaire"):
                parts = line.split(":", 1)
                value = ""
                if len(parts) > 1 and parts[1].strip():
                    value = parts[1].strip()
                else:
                    for next_idx in range(idx + 1, len(lines)):
                        if lines[next_idx].strip():
                            value = lines[next_idx].strip()
                            break
                if not value:
                    return ""
                if value.lower().startswith("réf affaire"):
                    value = value.split(":", 1)[-1].strip()
                return value
        return ""

    def _find_client_details(self, lines, blocks=None):
        return self._find_client_details_from_lines(lines)

    def _find_client_details_from_lines(self, lines):
        code_index = self._find_line_index(lines, "code client")
        if code_index is None:
            return {
                "nom": "",
                "adresse1": "",
                "adresse2": "",
                "cp": "",
                "ville": "",
                "tel": "",
                "email": "",
                "contact": "",
                "code_index": None,
            }
        client_nom = self._find_client_name_above(lines, code_index)
        address_lines = self._collect_client_address_lines(lines, code_index)
        contact, address_lines = self._extract_contact(address_lines)
        adresse1, adresse2, cp, ville = self._split_address_lines(address_lines)
        tel = self._find_phone(lines[code_index : code_index + 6])
        email = self._find_email(lines[code_index : code_index + 6])
        return {
            "nom": client_nom,
            "adresse1": adresse1,
            "adresse2": adresse2,
            "cp": cp,
            "ville": ville,
            "tel": tel,
            "email": email,
            "contact": contact,
            "code_index": code_index,
        }

    def _is_legal_noise(self, line: str) -> bool:
        return LEGAL_NOISE_RE.search(line) is not None

    def _find_client_name_above(self, lines: list[str], code_index: int) -> str:
        fallback = ""
        scan_start = max(code_index - 15, 0)
        for prev in range(code_index - 1, scan_start - 1, -1):
            candidate = self._clean_line(lines[prev])
            if not candidate:
                continue
            lowered = candidate.lower()
            if candidate.upper().startswith("DEVIS"):
                continue
            if lowered.startswith("date du devis"):
                continue
            if lowered.startswith("réf affaire"):
                continue
            if NOISE_HEADER_RE.search(lowered):
                continue
            if CP_VILLE_RE.search(candidate):
                continue
            if self._is_legal_noise(candidate):
                continue
            if self._looks_like_address_line(candidate):
                if not fallback and self._is_probable_company_name(candidate):
                    fallback = candidate
                continue
            if self._is_probable_company_name(candidate):
                return candidate
        return fallback

    def _collect_client_address_lines(self, lines: list[str], code_index: int) -> list[str]:
        collected = []
        for idx in range(code_index + 1, len(lines)):
            line = self._clean_line(lines[idx])
            if not line:
                continue
            lowered = line.lower()
            if CLIENT_STOP_RE.search(lowered):
                break
            if self._is_legal_noise(line):
                continue
            if "code client" in lowered:
                continue
            collected.append(line)
        return collected

    def _looks_like_address_line(self, value: str) -> bool:
        if STREET_HINT_RE.search(value):
            return True
        return bool(re.match(r"^\d+\s+\w+", value))

    def _find_line_index(self, lines: list[str], needle: str):
        needle_lower = needle.lower()
        for idx, line in enumerate(lines):
            if needle_lower in line.lower():
                return idx
        return None

    def _block_lines(self, text: str) -> list[str]:
        lines = []
        for line in text.splitlines():
            cleaned = self._clean_line(line)
            if cleaned:
                lines.append(cleaned)
        return lines

    def _find_block_containing(self, blocks: list[dict], needle: str):
        needle_lower = needle.lower()
        for block in blocks:
            if needle_lower in block["text"].lower():
                return block
        return None

    def _is_same_column(self, block: dict, anchor: dict) -> bool:
        x0, _, x1, _ = block["bbox"]
        ax0, _, ax1, _ = anchor["bbox"]
        overlap = min(x1, ax1) - max(x0, ax0)
        if overlap > 0:
            return True
        center = (x0 + x1) / 2
        anchor_center = (ax0 + ax1) / 2
        return abs(center - anchor_center) <= max(40, (ax1 - ax0) * 0.5)

    def _find_nearest_block_above(self, blocks: list[dict], anchor: dict):
        anchor_page = anchor["page_index"]
        _, ay0, _, _ = anchor["bbox"]
        candidates = []
        for block in blocks:
            if block["page_index"] != anchor_page:
                continue
            _, y0, _, y1 = block["bbox"]
            if y1 <= ay0 and block is not anchor:
                distance = ay0 - y1
                candidates.append((self._is_same_column(block, anchor), distance, block))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (not item[0], item[1]))
        return candidates[0][2]

    def _find_nearest_block_below(self, blocks: list[dict], anchor: dict):
        anchor_page = anchor["page_index"]
        _, _, _, ay1 = anchor["bbox"]
        candidates = []
        for block in blocks:
            if block["page_index"] != anchor_page:
                continue
            _, y0, _, _ = block["bbox"]
            if y0 >= ay1 and block is not anchor:
                distance = y0 - ay1
                candidates.append((self._is_same_column(block, anchor), distance, block))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (not item[0], item[1]))
        return candidates[0][2]

    def _blocks_below_anchor(self, blocks: list[dict], anchor: dict) -> list[dict]:
        anchor_page = anchor["page_index"]
        _, _, _, ay1 = anchor["bbox"]
        return [
            block
            for block in blocks
            if block["page_index"] == anchor_page and block["bbox"][1] >= ay1
        ]

    def _extract_contact(self, lines):
        filtered = []
        contact = ""
        for line in lines:
            match = re.search(r"contact\s*:?\s*(.+)", line, re.IGNORECASE)
            if match and not contact:
                contact = match.group(1).strip()
                continue
            filtered.append(line)
        return contact, filtered

    def _split_address_lines(self, address_lines):
        cp = ""
        ville = ""
        cp_candidates = []
        for idx, line in enumerate(address_lines):
            match = CP_VILLE_RE.search(line)
            if match:
                cp_candidates.append(
                    {
                        "cp": match.group(1),
                        "ville": match.group(2).strip(),
                        "prev_line": address_lines[idx - 1].strip() if idx > 0 else "",
                        "index": idx,
                    }
                )
        if not cp_candidates:
            adresse1 = address_lines[0] if address_lines else ""
            adresse2 = " ".join(address_lines[1:]) if len(address_lines) > 1 else ""
            return adresse1, adresse2, cp, ville
        cp_choice = self._choose_cp_ville(cp_candidates)
        cp = cp_choice["cp"]
        ville = cp_choice["ville"]
        remaining = [
            line for idx, line in enumerate(address_lines) if idx != cp_choice["index"]
        ]
        adresse1 = remaining[0] if remaining else ""
        adresse2 = " ".join(remaining[1:]) if len(remaining) > 1 else ""
        return adresse1, adresse2, cp, ville

    def _choose_cp_ville(self, candidates):
        best = None
        best_score = None
        for candidate in candidates:
            score = 0
            prev_line = candidate["prev_line"]
            if re.search(r"\d+", prev_line) and STREET_HINT_RE.search(prev_line):
                score += 3
            if self._is_majority_upper(candidate["ville"]):
                score += 1
            if LEGAL_NOISE_RE.search(prev_line):
                score -= 3
            if best_score is None or score > best_score:
                best_score = score
                best = candidate
        return best if best is not None else candidates[-1]

    def _is_majority_upper(self, value: str) -> bool:
        letters = [char for char in value if char.isalpha()]
        if not letters:
            return False
        upper_count = sum(1 for char in letters if char.isupper())
        return (upper_count / len(letters)) >= 0.6

    def _find_commercial_details(self, lines, blocks=None):
        return self._find_commercial_details_from_lines(lines)

    def _find_commercial_details_from_lines(self, lines):
        for idx, line in enumerate(lines):
            lowered = line.lower()
            if "contact commercial" in lowered:
                name = ""
                match = re.search(r"contact commercial\s*:\s*(.+)", line, re.IGNORECASE)
                if match:
                    candidate = self._clean_line(match.group(1))
                    if self._is_valid_commercial_name_candidate(candidate):
                        name = candidate
                if not name:
                    for next_idx in range(idx + 1, len(lines)):
                        candidate = self._clean_line(lines[next_idx])
                        if not candidate:
                            continue
                        if CP_VILLE_RE.search(candidate):
                            continue
                        if self._is_valid_commercial_name_candidate(candidate):
                            name = candidate
                            break
                if "contact commercial" in name.lower():
                    name = ""
                search_start = max(idx - 3, 0)
                search_lines = lines[search_start : idx + 11]
                return {
                    "nom": name,
                    "tel": self._find_phone(search_lines),
                    "email": self._find_email(search_lines),
                    "contact_index": idx,
                }
        return {"nom": "", "tel": "", "email": "", "contact_index": None}

    def _is_valid_commercial_name_candidate(self, candidate: str) -> bool:
        if not candidate:
            return False
        cleaned = self._clean_line(candidate)
        lowered = cleaned.lower()
        if CP_VILLE_RE.search(cleaned):
            return False
        if "@" in cleaned:
            return False
        if TEL_MARKER_RE.search(cleaned):
            return False
        if NOISE_HEADER_RE.search(lowered):
            return False
        if "contact commercial" in lowered:
            return False
        words = [word for word in cleaned.split() if LETTER_RE.search(word)]
        return len(words) >= 2

    def _is_invalid_client_name(self, candidate: str) -> bool:
        if not candidate:
            return True
        cleaned = self._clean_line(candidate)
        lowered = cleaned.lower()
        if "réalisé par" in lowered:
            return True
        if NOISE_HEADER_RE.search(lowered):
            return True
        if ":" in cleaned:
            return True
        return not self._is_probable_company_name(cleaned)

    def _is_invalid_commercial_name(self, candidate: str) -> bool:
        if not candidate:
            return True
        cleaned = self._clean_line(candidate)
        if CP_VILLE_RE.search(cleaned):
            return True
        return not self._is_valid_commercial_name_candidate(cleaned)

    def _build_ocr_zones(self, doc, blocks: list[dict]) -> list[dict]:
        zones = []
        code_block = self._find_block_containing(blocks, "code client")
        contact_block = self._find_block_containing(blocks, "contact commercial")
        if code_block:
            page = doc[code_block["page_index"]]
            page_rect = page.rect
            _, y0, _, _ = code_block["bbox"]
            band_height = 90
            rect = fitz.Rect(
                page_rect.x0,
                max(page_rect.y0, y0 - band_height),
                page_rect.x1,
                y0,
            )
            zones.append(
                {"page_index": code_block["page_index"], "rect": rect, "label": "code_client_above"}
            )
        if contact_block:
            page = doc[contact_block["page_index"]]
            page_rect = page.rect
            _, y0, _, y1 = contact_block["bbox"]
            rect = fitz.Rect(
                page_rect.x0,
                max(page_rect.y0, y0 - 40),
                page_rect.x1,
                min(page_rect.y1, y1 + 80),
            )
            zones.append(
                {"page_index": contact_block["page_index"], "rect": rect, "label": "contact_commercial"}
            )
        if not code_block:
            if doc.page_count:
                page = doc[0]
                page_rect = page.rect
                header_rect = fitz.Rect(
                    page_rect.x0,
                    page_rect.y0,
                    page_rect.x1,
                    min(page_rect.y1, page_rect.y0 + 120),
                )
                middle_rect = fitz.Rect(
                    page_rect.x0,
                    page_rect.y0 + page_rect.height * 0.35,
                    page_rect.x1,
                    page_rect.y0 + page_rect.height * 0.55,
                )
                zones.append({"page_index": 0, "rect": header_rect, "label": "fallback_header"})
                zones.append({"page_index": 0, "rect": middle_rect, "label": "fallback_middle"})
        return zones[:3]

    def _render_ocr_region(self, page, rect: fitz.Rect) -> Image.Image:
        pix = page.get_pixmap(clip=rect, dpi=300)
        mode = "RGBA" if pix.alpha else "RGB"
        return Image.frombytes(mode, [pix.width, pix.height], pix.samples)

    def _run_ocr_fallback(self, path: Path, blocks: list[dict], warnings: list[str]) -> list[dict]:
        ocr_results = []
        try:
            with fitz.open(path) as doc:
                zones = self._build_ocr_zones(doc, blocks)
                for zone in zones:
                    page = doc[zone["page_index"]]
                    image = self._render_ocr_region(page, zone["rect"])
                    text = ocr_image(image, lang="fr")
                    ocr_results.append(
                        {
                            "page_index": zone["page_index"],
                            "label": zone["label"],
                            "text": text.strip(),
                        }
                    )
        except OcrNotAvailableError as exc:
            warnings.append(f"WARNING: OCR Windows indisponible ({exc}).")
        except Exception as exc:  # pylint: disable=broad-except
            warnings.append(f"WARNING: échec OCR Windows ({exc}).")
        return ocr_results

    def _find_phone(self, lines):
        for line in lines:
            match = PHONE_RE.search(line)
            if match:
                return match.group(0).strip()
        return ""

    def _find_email(self, lines):
        for line in lines:
            match = EMAIL_RE.search(line)
            if match:
                return match.group(0).strip()
        return ""

    def _run_internal_debug_test(self, path: Path, data: dict, warnings: list[str]) -> None:
        if path.name != "SRX2511AFF037501_20251202_161449.pdf":
            return
        failures = []
        if data.get("client_nom") != "BERVAL MAISONS":
            failures.append("client_nom attendu 'BERVAL MAISONS'")
        if CP_VILLE_RE.search(data.get("commercial_nom", "")):
            failures.append("commercial_nom ne doit pas matcher CP/Ville")
        if "contact commercial" in data.get("commercial_nom", "").lower():
            failures.append("commercial_nom ne doit pas contenir 'Contact commercial'")
        if data.get("client_cp") != "77100":
            failures.append("client_cp attendu '77100'")
        if failures:
            warnings.append("SRX DEBUG TEST FAILED: " + "; ".join(failures))

    def export_debug(self, path: Path) -> Path | None:
        payload = self._debug_cache.get(path)
        if not payload:
            return None
        output_path = path.with_suffix(".debug.txt")
        with output_path.open("w", encoding="utf-8") as handle:
            handle.write("=== LIGNES EXTRAITES ===\n")
            for line in payload.get("lines", []):
                handle.write(f"{line}\n")
            handle.write("\n=== BLOCKS ===\n")
            for block in payload.get("blocks", []):
                bbox = block["bbox"]
                handle.write(
                    f"[page {block['page_index']}] bbox={bbox} text={block['text']}\n"
                )
            handle.write("\n=== OCR ===\n")
            for snapshot in payload.get("ocr", []):
                handle.write(
                    f"[page {snapshot['page_index']}] {snapshot['label']}:\n{snapshot['text']}\n\n"
                )
        return output_path

    def _find_modele(self, lines):
        for line in lines:
            match = re.search(r"-\s*Mod[eè]le\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_finitions(self, lines):
        finitions = {}
        in_finition = False
        for line in lines:
            if "FINITION" in line.upper():
                in_finition = True
                continue
            if in_finition and not line.strip().startswith("-"):
                if finitions:
                    break
                continue
            if not in_finition:
                continue
            match = re.search(r"-\s*([^:]+)\s*:\s*(.+)", line)
            if not match:
                continue
            label = match.group(1).strip().lower()
            value = match.group(2).strip()
            if label.startswith("marche"):
                finitions["marche"] = value
            elif label.startswith("structure"):
                finitions["structure"] = value
            elif label.startswith("main courante"):
                finitions["main_courante"] = value
            elif label.startswith("contremarche"):
                finitions["contremarche"] = value
            elif label.startswith("rampe"):
                finitions["rampe"] = value
        return finitions

    def _extract_essence(self, values: list[str]) -> str:
        for value in values:
            if not value:
                continue
            match = ESSENCE_RE.search(value)
            if match:
                return match.group(0)
        for value in values:
            if not value:
                continue
            if re.search(r"\b[eé]paisseur\b", value, re.IGNORECASE):
                continue
            parts = value.split("-", 1)
            essence = parts[0].strip()
            if len(essence) >= 3 and LETTER_RE.search(essence):
                return essence
        return ""

    def _find_main_courante(self, lines):
        for line in lines:
            match = re.search(r"-\s*Main\s+courante\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                scellement = ""
                if "scellement" in value.lower():
                    scellement = value
                return value, scellement
        return "", ""

    def _find_nez_de_marches(self, lines):
        for line in lines:
            match = re.search(r"-\s*Nez\s+de\s+marche[s]?\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _find_tete_poteau(self, lines):
        for line in lines:
            if "TPA" in line and re.search(r"Poteau", line, re.IGNORECASE):
                return "TPA"
        return ""

    def _find_poteaux_depart(self, lines):
        for line in lines:
            if re.search(r"poteau[x]?\s+de\s+d[eé]part", line, re.IGNORECASE):
                match = re.search(r":\s*(.+)", line)
                if match:
                    value = match.group(1).strip()
                    value = re.sub(r"\([^)]*\)", "", value).strip()
                    return value
        return "" 

    def _find_pose_details(self, lines):
        pose_amount = ""
        pose_sold = False
        saw_prestations = False
        for line in lines:
            if "PRESTATIONS" in line.upper():
                saw_prestations = True
                continue
            if not saw_prestations:
                continue
            if re.search(r"\bpose\b", line, re.IGNORECASE):
                amount = self._extract_pose_amount(line)
                if amount:
                    pose_sold = True
                    pose_amount = amount
                    break
        return pose_sold, pose_amount

    def _extract_pose_amount(self, line: str) -> str:
        euro_matches = re.findall(
            r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})\s*€", line
        )
        if euro_matches:
            return self._normalize_amount(euro_matches[-1])
        matches = AMOUNT_RE.findall(line)
        if not matches:
            return ""
        for match in reversed(matches):
            normalized = self._normalize_amount(match)
            if normalized not in {"1,00", "1.00"}:
                return normalized
        return ""
