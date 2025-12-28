import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber


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
CODE_CLIENT_RE = re.compile(r"\bcode\s*client\b", re.IGNORECASE)
STREET_HINT_RE = re.compile(
    r"\b(rue|allee|all[ée]e|avenue|av\.?|bd|boulevard|chemin|route|impasse|zac|za)\b",
    re.IGNORECASE,
)
LEGAL_NOISE_RE = re.compile(
    r"\b(sas|sarl|rcs|r\.c\.s|naf|siret|capital|eur|au capital)\b|b\s?\d+",
    re.IGNORECASE,
)
TEL_MARKER_RE = re.compile(r"\b(t[eé]l|tel|fax)\b", re.IGNORECASE)
ADDRESS_STOP_RE = re.compile(
    r"(t[eé]l|tel|fax|mail|email|contact\s+commercial|validit[eé]|d[ée]signation)",
    re.IGNORECASE,
)
BANNED_CLIENT_TOKENS = ("devis", "réalisé par", "riaux", "vaugarny", "bazouges", "35560")
DEVIS_LINE_RE = re.compile(r"DEVIS\s*N[°º]?\s*(SRX\S+)", re.IGNORECASE)
ESSENCE_RE = re.compile(
    r"\b(ch[eê]ne|h[eê]tre|fr[eê]ne|sapin|pin|hêtre|chêne)\b", re.IGNORECASE
)


class DevisParser:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def _clean_line(self, value: str) -> str:
        value = re.sub(r"[^\wÀ-ÖØ-öø-ÿ&'()/\-\., :°]", " ", value)
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
        text = self._extract_text(path)
        lines = [line.strip() for line in text.splitlines()]
        return self._parse_lines(lines, path)

    def _parse_lines(self, lines: list[str], path: Path | None = None) -> dict:
        warnings = []
        normalized_lines = [self._clean_line(line) for line in lines if line is not None]
        if not normalized_lines:
            warnings.append("Texte du devis illisible ou vide.")

        fourniture_ht = self._find_amount_by_label(
            normalized_lines, r"PRIX DE LA FOURNITURE HT\s*:\s*([\d\s]+,\d{2})"
        )
        prestations_ht = self._find_amount_by_label(
            normalized_lines, r"PRIX PRESTATIONS ET SERVICES HT\s*:\s*([\d\s]+,\d{2})"
        )
        total_ht = self._find_amount_by_label(
            normalized_lines, r"TOTAL HORS TAXE\s*:\s*([\d\s]+,\d{2})"
        )
        devis_full, devis_num, devis_type = self._find_devis_reference(normalized_lines)
        ref_affaire = self._find_ref_affaire(normalized_lines)
        client_details = self._find_client_details(normalized_lines)
        commercial_details = self._find_commercial_details(normalized_lines)
        esc_gamme = self._find_modele(normalized_lines)
        finitions = self._extract_finitions(normalized_lines)
        esc_finition_marches = finitions.get("marche", "")
        esc_finition_structure = finitions.get("structure", "")
        esc_finition_mains_courante = finitions.get("main_courante", "")
        esc_finition_contremarche = finitions.get("contremarche", "")
        esc_finition_rampe = finitions.get("rampe", "")
        remplissage = self._extract_remplissage(normalized_lines, warnings)
        esc_main_courante, esc_main_courante_scellement = self._find_main_courante(
            normalized_lines
        )
        esc_nez_de_marches = self._find_nez_de_marches(normalized_lines)
        esc_essence = self._extract_essence(
            [
                esc_finition_marches,
                esc_finition_structure,
                esc_finition_mains_courante,
                esc_finition_contremarche,
                esc_finition_rampe,
            ]
        )
        esc_tete_de_poteau = self._find_tete_poteau(normalized_lines)
        esc_poteaux_depart = self._find_poteaux_depart(normalized_lines)
        pose_sold, pose_amount = self._find_pose_details(normalized_lines)

        srx_debug = self.debug and path and "SRX2511AFF037501" in path.name
        if client_details["nom"] and any(
            banned in client_details["nom"].lower() for banned in ("réalisé par",)
        ):
            dump = self._dump_lines_around(normalized_lines, client_details.get("code_index"))
            warnings.append(
                "Client: nom contient 'Réalisé par'.\n"
                f"[PARSE] context around Code client:\n{dump}"
            )
        if CP_VILLE_RE.search(commercial_details["nom"]):
            dump = self._dump_lines_around(normalized_lines, commercial_details.get("contact_index"))
            warnings.append(
                "Commercial: nom ressemble à un CP/Ville.\n"
                f"[PARSE] context around contact commercial:\n{dump}"
            )
        if srx_debug:
            if "réalisé par" in client_details["nom"].lower():
                warnings.append("Client SRX: nom contient 'Réalisé par'.")
            if CP_VILLE_RE.search(commercial_details["nom"]):
                warnings.append("Client SRX: nom commercial ressemble à un CP/Ville.")
        if not devis_num:
            warnings.append("Devis SRX introuvable.")
        if not ref_affaire:
            warnings.append("Réf affaire introuvable.")
        if not client_details["nom"]:
            warnings.append("Client introuvable (ancre 'Code client').")

        data = {
            "lines": normalized_lines,
            "fourniture_ht": fourniture_ht,
            "prestations_ht": prestations_ht,
            "total_ht": total_ht,
            "devis_annee_mois": devis_full,
            "devis_num": devis_num,
            "devis_type": devis_type,
            "ref_affaire": ref_affaire,
            "client_nom": client_details["nom"],
            "client_adresse1": client_details["adresse1"],
            "client_adresse2": client_details["adresse2"],
            "client_adresse": client_details["adresse"],
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
            "esc_section_remplissage_garde_corps_rampant": remplissage["rampant"],
            "esc_section_remplissage_garde_corps_etage": remplissage["etage"],
            "esc_remplissage_garde_corps_soubassement": remplissage["soubassement"],
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
                f"devis_annee_mois={devis_full}",
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
                f"esc_remplissage_rampant={remplissage['rampant']}",
                f"esc_remplissage_etage={remplissage['etage']}",
                f"esc_remplissage_soubassement={remplissage['soubassement']}",
                f"esc_essence={esc_essence}",
                f"esc_main_courante={esc_main_courante}",
                f"esc_main_courante_scellement={esc_main_courante_scellement}",
                f"esc_nez_de_marches={esc_nez_de_marches}",
                f"esc_tete_de_poteau={esc_tete_de_poteau}",
                f"esc_poteaux_depart={esc_poteaux_depart}",
            ]
            if srx_debug and path:
                data["debug"].extend(
                    [
                        f"srx_client_nom={client_details['nom']}",
                        f"srx_client_cp_ville={client_details['cp']} {client_details['ville']}",
                        f"srx_commercial_nom={commercial_details['nom']}",
                    ]
                )
            self._run_internal_debug_test(path or Path(""), data, warnings)
        return data

    def _extract_text(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(path)
        text_parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
        return "\n".join(text_parts)

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
            match = DEVIS_LINE_RE.search(line)
            if match:
                full_value = match.group(0).strip()
                sr = match.group(1)
                sr_match = SRX_RE.search(sr)
                num = sr_match.group("num") if sr_match else ""
                srx_type = sr_match.group("type") if sr_match else ""
                return full_value, num, srx_type
        return "", "", ""

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

    def _find_client_details(self, lines):
        code_index = None
        for idx, line in enumerate(lines):
            if CODE_CLIENT_RE.search(line):
                code_index = idx
                break
        defaults = {
            "nom": "",
            "adresse1": "",
            "adresse2": "",
            "adresse": "",
            "cp": "",
            "ville": "",
            "tel": "",
            "email": "",
            "contact": "",
            "code_index": None,
        }
        if code_index is None:
            return defaults

        client_nom = ""
        name_line_index = code_index
        idx = code_index + 1
        while idx < len(lines):
            candidate = self._clean_line(lines[idx])
            if not candidate:
                idx += 1
                continue
            if self._is_address_stop(candidate):
                break
            if self._is_banned_client_line(candidate):
                idx += 1
                continue
            client_nom = candidate
            name_line_index = idx
            break
        address_lines = []
        idx = name_line_index + 1
        while idx < len(lines):
            candidate = self._clean_line(lines[idx])
            idx += 1
            if not candidate:
                continue
            if self._is_address_stop(candidate):
                break
            address_lines.append(candidate)
        contact, address_lines = self._extract_contact(address_lines)
        adresse1, adresse2, cp, ville = self._split_address_lines(address_lines)
        tel = self._find_phone(lines[code_index : code_index + 6])
        email = self._find_email(lines[code_index : code_index + 6])
        full_address_lines = list(address_lines)
        cp_ville_line = " ".join(part for part in (cp, ville) if part).strip()
        if cp_ville_line:
            full_address_lines.append(cp_ville_line)
        return {
            "nom": client_nom,
            "adresse1": adresse1,
            "adresse2": adresse2,
            "adresse": "\n".join(line for line in full_address_lines if line),
            "cp": cp,
            "ville": ville,
            "tel": tel,
            "email": email,
            "contact": contact,
            "code_index": code_index,
        }

    def _is_legal_noise(self, line: str) -> bool:
        return LEGAL_NOISE_RE.search(line) is not None

    def _is_address_stop(self, line: str) -> bool:
        return bool(ADDRESS_STOP_RE.search(line))

    def _is_banned_client_line(self, line: str) -> bool:
        lowered = line.lower()
        return any(token in lowered for token in BANNED_CLIENT_TOKENS)

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

    def _find_commercial_details(self, lines):
        for idx, line in enumerate(lines):
            lowered = line.lower()
            if "contact commercial" in lowered:
                name = ""
                for next_idx in range(idx + 1, min(idx + 9, len(lines))):
                    candidate = self._clean_line(lines[next_idx])
                    if not candidate:
                        continue
                    if CP_VILLE_RE.search(candidate):
                        continue
                    if TEL_MARKER_RE.search(candidate):
                        continue
                    if "@" in candidate:
                        continue
                    if NOISE_HEADER_RE.search(candidate.lower()):
                        continue
                    name = candidate
                    break
                search_start = max(idx - 3, 0)
                search_lines = lines[search_start : idx + 11]
                return {
                    "nom": name,
                    "tel": self._find_phone(search_lines),
                    "email": self._find_email(search_lines),
                    "contact_index": idx,
                }
        return {"nom": "", "tel": "", "email": "", "contact_index": None}


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

    def _extract_remplissage(self, lines: list[str], warnings: list[str]) -> dict:
        result = {"rampant": "", "etage": "", "soubassement": ""}
        fallback_value = ""
        for line in lines:
            lowered = line.lower()
            if "remplissage" not in lowered:
                continue
            match = re.search(r"remplissage[^:]*:\s*(.+)", line, re.IGNORECASE)
            value = match.group(1).strip() if match else ""
            if "rampant" in lowered:
                result["rampant"] = value or result["rampant"]
            elif "etage" in lowered or "étage" in lowered:
                result["etage"] = value or result["etage"]
            elif "soubassement" in lowered:
                result["soubassement"] = value or result["soubassement"]
            elif not fallback_value:
                fallback_value = value
        if fallback_value and not any(result.values()):
            result["rampant"] = fallback_value
            warnings.append("Remplissage sans précision: affecté au rampant par défaut.")
        return result

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
