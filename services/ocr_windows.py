import asyncio
import io

from PIL import Image


class OcrNotAvailableError(RuntimeError):
    pass


async def _recognize_bytes(image_bytes: bytes, lang: str) -> str:
    try:
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
    except Exception as exc:  # pylint: disable=broad-except
        raise OcrNotAvailableError(
            "WinRT OCR indisponible: modules WinRT non accessibles."
        ) from exc

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(image_bytes)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = OcrEngine.try_create_from_language(Language(lang))
    if engine is None:
        engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrNotAvailableError("WinRT OCR indisponible: engine non trouvé.")
    result = await engine.recognize_async(bitmap)
    return result.text or ""


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    temp_loop = asyncio.new_event_loop()
    try:
        return temp_loop.run_until_complete(coro)
    finally:
        temp_loop.close()


def ocr_image(pil_image: Image.Image, lang: str = "fr") -> str:
    if pil_image is None:
        return ""
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return _run_async(_recognize_bytes(buffer.getvalue(), lang))
