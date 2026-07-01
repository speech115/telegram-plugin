"""Pure helpers for pulling downloadable file_ids out of TDLib Message objects.

Works directly on pytdbot's native typed objects (pytdbot.types.Message and
friends), not on dicts: pytdbot's to_dict() only converts the top level of an
object, leaving nested fields (e.g. Message.content) as native typed objects,
so dict-shaped fixtures don't reflect what a live call actually returns.
Native pytdbot types support subscript access (obj["field"]) directly.

TDLib content schema reference: https://core.telegram.org/tdlib/docs/classtd_1_1td__api_1_1_message.html
"""


def extract_file_id_from_message(message) -> int:
    content = message["content"]
    content_type = content.getType()
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
