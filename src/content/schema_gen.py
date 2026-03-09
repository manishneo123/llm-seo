"""Generate FAQ / Article / HowTo JSON-LD from draft content."""
import json
import re


def generate_faq_schema(body_md: str, title: str) -> str:
    """Extract potential Q&A from headings and first lines; build FAQPage schema."""
    lines = body_md.split("\n")
    questions = []
    in_heading = False
    for i, line in enumerate(lines):
        if line.startswith("## ") or line.startswith("### "):
            q = line.lstrip("#").strip()
            if q and len(q) > 10:
                # Use next non-empty line as answer snippet
                ans = ""
                for j in range(i + 1, min(i + 5, len(lines))):
                    if lines[j].strip() and not lines[j].startswith("#"):
                        ans = lines[j].strip()[:200]
                        break
                questions.append({"question": q, "answer": ans or q})
    if len(questions) > 5:
        questions = questions[:5]
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q["question"], "acceptedAnswer": {"@type": "Answer", "text": q["answer"]}}
            for q in questions
        ],
    }
    return json.dumps(schema, indent=2)


def generate_article_schema(title: str, body_preview: str, slug: str | None = None) -> str:
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": body_preview[:200] if body_preview else title,
    }
    if slug:
        schema["url"] = slug
    return json.dumps(schema, indent=2)


def generate_schema(brief_schema_type: str, title: str, body_md: str, slug: str | None = None) -> str:
    if brief_schema_type and "FAQ" in brief_schema_type:
        return generate_faq_schema(body_md, title)
    return generate_article_schema(title, (body_md or "").split("\n")[0][:200], slug)
