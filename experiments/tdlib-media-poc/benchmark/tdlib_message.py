"""Pure helpers for pulling downloadable file_ids out of TDLib Message objects.

TDLib content schema reference: https://core.telegram.org/tdlib/docs/classtd_1_1td__api_1_1_message.html
"""


def extract_file_id_from_message(message: dict) -> int:
    content = message.get("content") or {}
    content_type = content.get("@type", "")
    if content_type == "messageVideo":
        return content["video"]["video"]["id"]
    if content_type == "messageDocument":
        return content["document"]["document"]["id"]
    if content_type == "messagePhoto":
        sizes = content["photo"]["sizes"]
        return sizes[-1]["photo"]["id"]
    if content_type == "messageAudio":
        return content["audio"]["audio"]["id"]
    raise ValueError(f"unsupported message content type for download: {content_type!r}")
