from __future__ import annotations

import json
from urllib.parse import parse_qs, unquote, urlparse

from litkg.verify import Response

HE_2016 = {
    "type": "paper-conference",
    "title": "Deep Residual Learning for Image Recognition",
    "author": [
        {"family": "He", "given": "Kaiming"},
        {"family": "Zhang", "given": "Xiangyu"},
        {"family": "Ren", "given": "Shaoqing"},
        {"family": "Sun", "given": "Jian"},
    ],
    "issued": {"date-parts": [[2016, 6]]},
    "container-title": "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)",
    "DOI": "10.1109/CVPR.2016.90",
}

BERT = {
    "type": "proceedings-article",
    "title": ["BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"],
    "author": [
        {"family": "Devlin", "given": "Jacob"},
        {"family": "Chang", "given": "Ming-Wei"},
        {"family": "Lee", "given": "Kenton"},
        {"family": "Toutanova", "given": "Kristina"},
    ],
    "issued": {"date-parts": [[2019]]},
    "container-title": ["Proceedings of the 2019 Conference of the North"],
    "DOI": "10.18653/v1/N19-1423",
}

UNRELATED = {
    "type": "journal-article",
    "title": ["A Survey of Soil Microbiomes"],
    "author": [{"family": "Green", "given": "Alice"}],
    "issued": {"date-parts": [[2015]]},
    "DOI": "10.1000/soil.2015.1",
}


def atom(*entries: dict) -> str:
    body = "".join(
        "<entry>"
        f"<id>http://arxiv.org/abs/{entry['id']}v1</id>"
        f"<published>{entry['year']}-06-12T17:57:34Z</published>"
        f"<title>{entry['title']}</title>"
        + "".join(f"<author><name>{name}</name></author>" for name in entry["authors"])
        + "</entry>"
        for entry in entries
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">{body}</feed>'


ARXIV = {
    "1706.03762": {
        "id": "1706.03762",
        "year": 2017,
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"],
    },
    "2001.08361": {
        "id": "2001.08361",
        "year": 2020,
        "title": "Scaling Laws for Neural Language Models",
        "authors": ["Jared Kaplan", "Sam McCandlish", "Tom Henighan"],
    },
}


class FakeFetcher:
    """Replays registry responses. ``dois`` maps DOI -> CSL item, ``works`` feed title searches."""

    def __init__(self, dois=None, works=None, arxiv=None, openalex=None, fail_hosts=()):
        self.dois = {key.lower(): value for key, value in (dois if dois is not None else {"10.1109/cvpr.2016.90": HE_2016, "10.18653/v1/n19-1423": BERT}).items()}
        self.works = works if works is not None else [BERT, HE_2016, UNRELATED]
        self.arxiv = arxiv if arxiv is not None else ARXIV
        self.openalex = openalex or []
        self.fail_hosts = set(fail_hosts)
        self.requests: list[str] = []

    def get(self, url: str, accept: str = "application/json") -> Response:
        self.requests.append(url)
        parsed = urlparse(url)
        if parsed.hostname in self.fail_hosts:
            from litkg.verify import LookupFailed

            raise LookupFailed(f"{parsed.hostname}: connection refused")
        query = parse_qs(parsed.query)
        if parsed.hostname == "doi.org":
            item = self.dois.get(unquote(parsed.path.lstrip("/")).lower())
            return Response(200, json.dumps(item)) if item else Response(404, "")
        if parsed.hostname == "export.arxiv.org":
            entry = self.arxiv.get(query["id_list"][0])
            return Response(200, atom(entry) if entry else atom())
        if parsed.hostname == "api.crossref.org":
            words = set(query["query.bibliographic"][0].lower().split())
            items = [item for item in self.works if words & set(str(item["title"]).lower().split())]
            return Response(200, json.dumps({"message": {"items": items}}))
        if parsed.hostname == "api.openalex.org":
            return Response(200, json.dumps({"results": self.openalex}))
        return Response(404, "")
