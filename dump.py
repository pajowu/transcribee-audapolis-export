import re

import automerge
import inquirer
import requests
import websockets
import enum
import asyncio
import tempfile
import zipfile
import json
import uuid


class SyncMessageType(enum.IntEnum):
    CHANGE = 1
    CHANGE_BACKLOG_COMPLETE = 2
    FULL_DOCUMENT = 3


def get_token(username: str, password: str):
    req = requests.post(
        "http://localhost:8000/api/v1/users/login/",
        json={"username": username, "password": password},
    )
    req.raise_for_status()
    return req.json()["token"]


def get_documents(token: str):
    req = requests.get(
        "http://localhost:8000/api/v1/documents",
        headers={"Authorization": f"Token {token}"},
    )
    req.raise_for_status()
    return req.json()


async def dump_doc(token: str, doc_id: str):
    websocket_base_url = "ws://localhost:8000/sync/"
    doc = automerge.init({})
    async with websockets.connect(
        f"{websocket_base_url}documents/{doc_id}/"
    ) as websocket:
        while True:
            msg = await websocket.recv()
            if msg[0] == SyncMessageType.CHANGE:
                automerge.apply_changes(doc, [msg[1:]])
            elif msg[0] == SyncMessageType.CHANGE_BACKLOG_COMPLETE:
                return doc
            elif msg[0] == SyncMessageType.FULL_DOCUMENT:
                doc = automerge.load(msg[1:])


def dump_doc_sync(token: str, doc_id: str):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(dump_doc(token, doc_id))


def get_doc_metadata(token: str, doc_id: str):
    req = requests.get(
        f"http://localhost:8000/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Token {token}"},
    )
    req.raise_for_status()
    return req.json()


def get_doc_audio_bytes(doc_metadata):
    audio_url = doc_metadata["audio_file"]
    req = requests.get(audio_url)
    req.raise_for_status()
    return req.content


def transform_content(doc, source):
    """Transforms the transcribee paragraphs into the audapolis format.

    Note: This does not add `non_text` elements between text elements and does
    not try to fix timing errors. See `repair_content` for that.
    """
    content = []
    current_text = None
    current_start = None
    current_end = None
    current_conf = None
    current_conf_n = None
    for paragraph in doc["paragraphs"]:
        content.append(
            {
                "type": "paragraph_start",
                "uuid": str(uuid.uuid4()),
                "speaker": paragraph["speaker"] or "Unknown",
                "language": paragraph["lang"],
            }
        )
        for i, token in enumerate(paragraph["children"]):
            if current_text is None:
                current_text = token["text"]
                current_start = token["start"]
                current_end = token["end"]
                current_conf = token["conf"]
                current_conf_n = 1
                continue
            if token["text"].startswith(" "):  # New word
                content.append(
                    {
                        "type": "text",
                        "uuid": str(uuid.uuid4()),
                        "source": source,
                        "sourceStart": current_start / 1000,
                        "length": (current_end - current_start) / 1000,
                        "text": current_text,
                        "conf": current_conf / current_conf_n,
                    }
                )
                current_text = token["text"]
                current_start = max(current_end, token["start"])
                current_end = token["end"]
                current_conf = token["conf"]
                current_conf_n = 1
            else:
                current_text += token["text"]
                current_end = max(current_end, token["end"])
                current_conf += token["conf"]
                current_conf_n += 1

        if current_text is not None:
            content.append(
                {
                    "type": "text",
                    "uuid": str(uuid.uuid4()),
                    "source": source,
                    "sourceStart": current_start / 1000,
                    "length": (current_end - current_start) / 1000,
                    "text": current_text,
                    "conf": current_conf / current_conf_n,
                }
            )
            current_text = None
            current_start = None
            current_end = None
            current_conf = None
            current_conf_n = None
        content.append(
            {
                "type": "paragraph_end",
                "uuid": str(uuid.uuid4()),
            }
        )
    return content


def repair_content(transformed_content, source):
    """Takes a audapolis content list and tries to correct some errors.

    This works on the assumption that the content only describes one document from start to finish with no repetitions.

    This functions adds `non_text` elements if there is a space between to consecutive `text` tokens.
    If a `text` token starts earlier than the previous ended, it moves the start of the token to the end of the previous token.
    """
    repaired_content = []
    last_end = 0
    for item in transformed_content:
        if item["type"] != "text":
            repaired_content.append(item)
        else:
            if item["sourceStart"] > last_end:
                repaired_content.append(
                    {
                        "type": "non_text",
                        "uuid": str(uuid.uuid4()),
                        "source": source,
                        "sourceStart": last_end,
                        "length": (item["sourceStart"] - last_end),
                    }
                )
            if item["sourceStart"] < last_end:
                end = item["sourceStart"] + item["length"]
                item["sourceStart"] = last_end
                item["length"] = end - last_end
            repaired_content.append(item)
            last_end = item["sourceStart"] + item["length"]
    return repaired_content


questions = [
    inquirer.Text("name", message="What's your username"),
    inquirer.Password("password", message="What's your password"),
]
answers = inquirer.prompt(questions)


token = get_token(username=answers["name"], password=answers["password"])

docs = get_documents(token)


questions = [
    inquirer.List(
        "document",
        message="What size do you need?",
        choices=[(d["name"], d["id"]) for d in docs],
    ),
]
answers = inquirer.prompt(questions)

doc_id = answers["document"]

doc = dump_doc_sync(token, doc_id)
doc = automerge.dump(doc)

doc_metadata = get_doc_metadata(token, doc_id)

doc_audio_bytes = get_doc_audio_bytes(doc_metadata)
transformed_document = {
    "version": 3,
    "metadata": {"display_video": False, "display_speaker_names": True},
    "content": repair_content(transform_content(doc, doc_id), doc_id),
}
with zipfile.ZipFile(f"{doc_id}.audapolis", "w") as zf:
    with zf.open(f"sources/{doc_id}", "w") as f:
        f.write(doc_audio_bytes)

    with zf.open(f"document.json", "w") as f:
        f.write(json.dumps(transformed_document).encode())
