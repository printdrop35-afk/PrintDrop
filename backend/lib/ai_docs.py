"""AI documents for the customer portal: 13 selected templates (catalogue mirrors ProDocOnline's names),
AI drafting (Claude via the Emergent key) and A4 PDF rendering. Free for PrintDrop customers."""

import io
import json
import logging
import os
import re
import uuid
from html import escape

from emergentintegrations.llm.chat import LlmChat, StreamDone, TextDelta, UserMessage
from fastapi import HTTPException
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

logger = logging.getLogger(__name__)

PRODOCONLINE_CATALOGUE_URL = "https://prodoconline.com/documents"
MODEL = ("anthropic", "claude-sonnet-5-5")


def _f(key: str, label: str, required: bool = True, multiline: bool = False, placeholder: str = "") -> dict:
    return {"key": key, "label": label, "required": required, "multiline": multiline, "placeholder": placeholder}


NAME = _f("full_name", "Vos nom et prénom")
CONTACT = _f("contact", "Vos coordonnées (adresse, téléphone, e-mail)", required=False, multiline=True)
DETAILS = _f("details", "Informations complémentaires", required=False, multiline=True, placeholder="Tout ce que l'IA doit savoir")
RECIPIENT = _f("recipient", "Destinataire (nom, organisme, adresse)", multiline=True)
COMPANY = _f("company", "Votre entreprise (nom, adresse, SIRET si disponible)", multiline=True)
CLIENT = _f("client", "Client (nom, adresse)", multiline=True)
LINES = _f("lines", "Prestations / articles (description, quantité, prix)", multiline=True,
           placeholder="Ex : Création logo — 1 — 300 €")

TEMPLATES: list[dict] = [
    # Documents personnels
    {"code": "cv", "name": "CV professionnel", "category": "Documents personnels",
     "fields": [NAME, CONTACT, _f("target", "Poste visé"), _f("experience", "Expériences (poste, entreprise, dates, missions)", multiline=True),
                _f("education", "Formation", multiline=True), _f("skills", "Compétences et langues", required=False, multiline=True)]},
    {"code": "cover_letter", "name": "Lettre de motivation", "category": "Documents personnels",
     "fields": [NAME, CONTACT, _f("company_target", "Entreprise et poste visés"),
                _f("motivation", "Pourquoi ce poste ? Vos atouts", multiline=True), DETAILS]},
    {"code": "resignation", "name": "Lettre de démission", "category": "Documents personnels",
     "fields": [NAME, CONTACT, _f("employer", "Employeur (nom, adresse)", multiline=True), _f("position", "Votre poste"),
                _f("notice", "Date de départ souhaitée / préavis"), DETAILS]},
    {"code": "admin_letter", "name": "Lettre administrative", "category": "Documents personnels",
     "fields": [NAME, CONTACT, RECIPIENT, _f("subject", "Objet de la lettre"), _f("request", "Votre demande en quelques mots", multiline=True),
                _f("reference", "Référence de dossier (n° allocataire, fiscal…)", required=False)]},
    # Documents professionnels
    {"code": "invoice", "name": "Facture", "category": "Documents professionnels",
     "fields": [COMPANY, CLIENT, _f("number", "Numéro et date de la facture"), LINES,
                _f("vat", "TVA (taux, ou « TVA non applicable, art. 293 B du CGI »)"), _f("payment", "Conditions de paiement", required=False)]},
    {"code": "quote", "name": "Devis", "category": "Documents professionnels",
     "fields": [COMPANY, CLIENT, _f("number", "Numéro et date du devis"), LINES, _f("vat", "TVA (taux ou mention d'exonération)"),
                _f("validity", "Durée de validité et conditions", required=False)]},
    {"code": "business_letter", "name": "Lettre commerciale", "category": "Documents professionnels",
     "fields": [COMPANY, RECIPIENT, _f("subject", "Objet"), _f("message", "Message à transmettre (offre, relance, information…)", multiline=True)]},
    {"code": "business_proposal", "name": "Proposition commerciale", "category": "Documents professionnels",
     "fields": [COMPANY, CLIENT, _f("need", "Besoin du client", multiline=True), _f("solution", "Votre solution et ses avantages", multiline=True),
                _f("price", "Prix et délais", multiline=True)]},
    {"code": "business_plan", "name": "Business plan", "category": "Documents professionnels",
     "fields": [_f("project", "Nom et description du projet", multiline=True), _f("market", "Marché et clientèle visée", multiline=True),
                _f("strategy", "Stratégie commerciale", multiline=True), _f("finance", "Budget, financement, prévisions", multiline=True),
                _f("team", "Porteur(s) du projet", required=False, multiline=True)]},
    # Documents administratifs
    {"code": "complaint", "name": "Lettre de réclamation", "category": "Documents administratifs",
     "fields": [NAME, CONTACT, RECIPIENT, _f("issue", "Problème rencontré (dates, références, montants)", multiline=True),
                _f("expected", "Ce que vous demandez")]},
    {"code": "certificate", "name": "Attestation simple", "category": "Documents administratifs",
     "fields": [_f("issuer", "Personne qui atteste (nom, qualité, adresse)", multiline=True),
                _f("beneficiary", "Personne concernée"), _f("facts", "Ce qui est attesté", multiline=True), _f("place_date", "Lieu et date")]},
    {"code": "contract", "name": "Contrat simple", "category": "Documents administratifs",
     "fields": [_f("party_a", "Partie 1 (nom, adresse)", multiline=True), _f("party_b", "Partie 2 (nom, adresse)", multiline=True),
                _f("object", "Objet du contrat", multiline=True), _f("terms", "Prix, durée, obligations", multiline=True), DETAILS]},
]
TEMPLATE_BY_CODE = {t["code"]: t for t in TEMPLATES}

SYSTEM = (
    "Tu rédiges des documents professionnels en français, prêts à imprimer sur une page A4 ou plus. "
    "Utilise UNIQUEMENT les informations fournies ; si une information indispensable manque, laisse un champ "
    "entre crochets comme [à compléter] — n'invente jamais de nom, chiffre, date, numéro ou référence. "
    "Réponds STRICTEMENT par un objet JSON : {\"title\": \"titre court du document\", \"body\": \"contenu\"}. "
    "Dans body : texte brut, une ligne vide entre paragraphes, '## ' pour un intertitre, '- ' pour une puce. "
    "Pas de markdown gras/italique, pas de tableau."
)


def _llm_key() -> str:
    key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="La création de documents par IA n'est pas disponible pour le moment")
    return key


async def generate(template: dict, values: dict[str, str]) -> dict:
    missing = [f["label"] for f in template["fields"] if f["required"] and not values.get(f["key"], "").strip()]
    if missing:
        raise HTTPException(status_code=422, detail=f"Champ requis : {missing[0]}")
    infos = "\n".join(f"- {f['label']} : {values.get(f['key'], '').strip() or '(non renseigné)'}" for f in template["fields"])
    chat = LlmChat(api_key=_llm_key(), session_id=f"aidoc-{uuid.uuid4()}", system_message=SYSTEM).with_model(*MODEL)
    text = ""
    try:
        async for ev in chat.stream_message(UserMessage(text=f"Document : {template['name']}\nInformations :\n{infos}")):
            if isinstance(ev, TextDelta):
                text += ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as exc:  # provider error / timeout
        logger.warning("AI doc generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="L'IA n'a pas pu rédiger le document — réessayez dans un instant") from exc
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    body = str(data.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=502, detail="L'IA n'a pas renvoyé de document exploitable — réessayez")
    return {"title": str(data.get("title") or template["name"]).strip()[:150], "body": body[:20000]}


def render_pdf(title: str, body: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
                            title=title, author="PrintDrop")
    st_title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=10, alignment=TA_LEFT)
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4)
    st_p = ParagraphStyle("p", fontName="Helvetica", fontSize=10.5, leading=14.5, spaceAfter=6)
    flow: list = [Paragraph(escape(title), st_title)]
    bullets: list = []

    def flush() -> None:
        if bullets:
            flow.append(ListFlowable([ListItem(Paragraph(b, st_p), leftIndent=10) for b in bullets], bulletType="bullet", start="•", leftIndent=12))
            bullets.clear()

    for block in re.split(r"\n\s*\n", body.replace("\r", "")):
        for line in [block] if not block.lstrip().startswith(("- ", "## ")) else block.split("\n"):
            raw = line.strip()
            if not raw:
                continue
            if raw.startswith("## "):
                flush(); flow.append(Paragraph(escape(raw[3:]), st_h))
            elif raw.startswith("- "):
                bullets.append(escape(raw[2:]))
            else:
                flush(); flow.append(Paragraph(escape(raw).replace("\n", "<br/>"), st_p))
        flush()
    flow.append(Spacer(1, 4))
    doc.build(flow)
    return buf.getvalue()
