"""
CivicEye - AI Triage Module
Multimodal grievance analysis using the official google-genai SDK for Tumakuru, Karnataka.
"""

import os
import json
import logging
import mimetypes
import concurrent.futures
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables (.env) if present
load_dotenv()

logger = logging.getLogger("civiceye.ai_triage")

# Default Flash-class model
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
API_TIMEOUT_SECONDS = 10.0


# -----------------------------------------------------------------------------
# Pydantic Schema for Structured JSON Output
# -----------------------------------------------------------------------------

class TriageResult(BaseModel):
    detected_issue: str = Field(
        description="Concise plain-English label of the specific civic issue observed in the image."
    )
    image_matches_report: bool = Field(
        description="True if the photo genuinely shows the reported civic issue/category. False if irrelevant, selfie, indoors, meme, or unrelated."
    )
    severity: int = Field(
        ge=1,
        le=5,
        description="Integer severity rating from 1 (minor/cosmetic) to 5 (critical/life-threatening emergency)."
    )
    severity_reasons: List[str] = Field(
        min_length=2,
        max_length=4,
        description="List of 2 to 4 concise plain-English reasons justifying the assigned severity rating."
    )
    summary: str = Field(
        description="At most 2 concise sentences describing the problem and ground impact for municipal engineers."
    )
    suggested_action: str = Field(
        description="Clear, actionable recommendation for municipal field crews."
    )
    recommended_department_type: str = Field(
        description="The relevant municipal department category: exactly 'road', 'pollution', or 'water'."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 reflecting certainty in detection."
    )
    transcription: Optional[str] = Field(
        default=None,
        description="If citizen audio is attached, provide English translation/transcript of Kannada, Hindi or English speech. Return null if no audio was provided."
    )
    original_language: Optional[str] = Field(
        default=None,
        description="Spoken language: 'Kannada', 'Hindi', 'English', or null if no audio."
    )


# -----------------------------------------------------------------------------
# Category-Specific System Prompts for Tumakuru, Karnataka
# -----------------------------------------------------------------------------

CATEGORY_SYSTEM_PROMPTS = {
    "road": (
        "You are an expert municipal civil engineer and road safety surveyor for Tumakuru City Corporation and PWD Tumakuru Division in Karnataka, India.\n"
        "Your role is to analyze citizen-reported grievances and photographs concerning public roads, asphalt surfaces, pedestrian footpaths, curbs, and storm-drain covers.\n\n"
        "WHAT TO LOOK FOR IN TUMAKURU STREET CONTEXTS (e.g., MG Road, BH Road, residential layouts like Sadashivanagar/Batawadi):\n"
        "- Carriageway damage: potholes, craters, bitumen peeling, road cave-ins, sunken utility trenches.\n"
        "- Pedestrian infrastructure: broken concrete footpath slabs, open roadside drain covers, displaced interlocking pavers, tripping hazards.\n"
        "- Road edges & shoulders: erosion, severe shoulder drop-offs, crumbling curbs endangering two-wheelers and auto-rickshaws.\n"
        "- Unbarricaded hazards: open manholes, exposed reinforcing steel (rebar), unpaved muddy cuts across roads.\n\n"
        "SEVERITY SCALE (1 to 5):\n"
        "- 1 (Negligible / Cosmetic): Minor hairline surface cracks, faint weathering, slight aesthetic irregularity with no risk to vehicles or pedestrians.\n"
        "- 2 (Low): Shallow pothole (<2 inches) on a quiet residential lane, minor chipped footpath slab; walkable and passable.\n"
        "- 3 (Moderate): Medium pothole (2–4 inches deep), broken footpath slab creating a real tripping risk, or deteriorated road edge forcing vehicles inward.\n"
        "- 4 (High): Deep crater (>4 inches) on an arterial or commercial road, open stormwater drain edge, sharp asphalt edge capable of causing two-wheeler skids/accidents.\n"
        "- 5 (Critical / Emergency): Extensive road collapse/cave-in, open deep manhole on busy roadway, or trench across main traffic lane causing immediate life safety danger.\n\n"
        "CRITICAL RULES:\n"
        "- If the image does not show a road, footpath, or outdoor civic infrastructure (e.g. a selfie, screenshot, indoor room, food, meme), set image_matches_report=False, severity=1, and confidence=0.9.\n"
        "- Keep summary to at most 2 sentences. Ensure recommended_department_type is 'road' (or 'water'/'pollution' if clearly miscategorized)."
    ),
    "pollution": (
        "You are an expert environmental health officer and sanitation inspector for the Tumakuru City Corporation Sanitation Wing and KSPCB Tumakuru in Karnataka, India.\n"
        "Your role is to inspect citizen-reported grievances and photographs regarding municipal solid waste, air pollution, garbage dumping, and sewage overflow.\n\n"
        "WHAT TO LOOK FOR IN TUMAKURU URBAN SETTINGS:\n"
        "- Solid waste: open garbage dumping points ('black spots'), overflowing dumper placers, unsegregated roadside refuse, discarded plastics.\n"
        "- Open burning: burning of dry leaves, mixed municipal waste, or plastics emitting toxic black or acrid smoke near dwellings or public areas.\n"
        "- Drainage & sanitation: overflowing open roadside gutters, stagnant black wastewater, blocked culverts, sewage pooling across roadways.\n"
        "- Debris & environmental hazards: illegal dumping of construction & demolition (C&D) waste on vacant plots, lake catchments, or walkways.\n\n"
        "SEVERITY SCALE (1 to 5):\n"
        "- 1 (Negligible): Isolated small litter item, single discarded wrapper or cup, harmless minor dust.\n"
        "- 2 (Low): Small waste heap on roadside, minor litter accumulation near a bin before routine collection.\n"
        "- 3 (Moderate): Established roadside black spot with decomposing solid waste, foul odor, or partially clogged open drain with stagnant water.\n"
        "- 4 (High): Active burning of garbage/plastic releasing dense smoke into residential or school zones, or sewage actively overflowing onto a pedestrian street.\n"
        "- 5 (Critical / Emergency): Massive hazardous/chemical waste dump, industrial effluent entering lake catchment or drinking water source, or hazardous open fire threatening nearby buildings.\n\n"
        "CRITICAL RULES:\n"
        "- If the photo does not depict garbage, waste, smoke, sewage, or pollution (e.g., unrelated screenshot, indoor selfie, random pet), set image_matches_report=False, severity=1, and confidence=0.9.\n"
        "- Keep summary to at most 2 sentences. Ensure recommended_department_type is 'pollution' (or 'water'/'road' if miscategorized)."
    ),
    "water": (
        "You are a senior municipal water supply engineer for the Tumakuru City Corporation Water Supply Division and KUWS&DB Tumakuru in Karnataka, India.\n"
        "Your role is to inspect citizen-reported grievances and photographs concerning municipal drinking water pipelines, valves, supply disruptions, and water quality.\n\n"
        "WHAT TO LOOK FOR IN TUMAKURU WATER NETWORK:\n"
        "- Pipeline leaks: treated municipal water leaking through road surfaces, bubbling water pools, leaking public standposts, leaking air release valves.\n"
        "- Pipeline bursts: ruptured distribution or feeder mains with pressurized water gushing onto the road causing erosion and flooding.\n"
        "- Contaminated water: muddy, discolored, turbid, or foul-smelling tap water supplied to residential or commercial connections.\n"
        "- Infrastructure faults: damaged distribution valves, missing valve covers, leaking supply meters, disconnected consumer ferrules.\n"
        "- Water outage indicators: dry taps, residents queueing with pots at dry points, non-functional public borewells.\n\n"
        "SEVERITY SCALE (1 to 5):\n"
        "- 1 (Negligible): Slow drip from a public tap or minor moisture seepage around a valve chamber with negligible loss.\n"
        "- 2 (Low): Steady minor trickle leaking into roadside drain; localized low water pressure.\n"
        "- 3 (Moderate): Continuous pipeline leak causing substantial potable water loss and localized waterlogging, or discolored tap water at a single household.\n"
        "- 4 (High): Major pipeline burst with pressurized water gushing onto carriageway, significant localized flooding, or brown/foul tap water across several homes.\n"
        "- 5 (Critical / Emergency): Major feeder trunk line rupture cutting off municipal supply to an entire ward, or direct cross-contamination where sewage has breached drinking water pipelines (acute public health epidemic risk).\n\n"
        "CRITICAL RULES:\n"
        "- If the photo does not depict water infrastructure, leaks, flooding, or contaminated water, set image_matches_report=False, severity=1, and confidence=0.9.\n"
        "- Keep summary to at most 2 sentences. Ensure recommended_department_type is 'water' (or 'road'/'pollution' if miscategorized)."
    ),
}


# -----------------------------------------------------------------------------
# Rule-Based Fallback Catalog (Used on timeout, missing key, or API error)
# -----------------------------------------------------------------------------

RULE_BASED_FALLBACKS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "road": {
        "Pothole": {
            "severity": 3,
            "reasons": [
                "Surface crater on road carriageway posing hazard to vehicles",
                "Increased accident risk for two-wheelers and auto-rickshaws",
            ],
            "action": "Inspect carriageway, clear loose stones, and patch with asphalt premix.",
        },
        "Broken footpath": {
            "severity": 2,
            "reasons": [
                "Damaged or displaced concrete paving slab on pedestrian walkway",
                "Tripping hazard for pedestrians, children, and elderly citizens",
            ],
            "action": "Replace broken paving slabs and restore smooth pedestrian walkway.",
        },
        "Damaged road edge": {
            "severity": 3,
            "reasons": [
                "Erosion and edge drop-off along the road shoulder",
                "Risk of two-wheeler skids and tyre damage when pulling over",
            ],
            "action": "Backfill and reinforce road shoulder with aggregate and bitumen seal.",
        },
        "default": {
            "severity": 2,
            "reasons": [
                "Reported road defect logged for routine field engineering inspection",
                "General municipal right-of-way maintenance required",
            ],
            "action": "Dispatch Tumakuru ward engineering staff for ground site assessment.",
        },
    },
    "pollution": {
        "Garbage burning": {
            "severity": 4,
            "reasons": [
                "Open waste burning releasing particulate matter and acrid smoke",
                "Immediate public health hazard and environmental air quality violation",
            ],
            "action": "Extinguish burning waste immediately and penalize open burning violation.",
        },
        "Garbage dump": {
            "severity": 3,
            "reasons": [
                "Accumulation of unsegregated solid waste on public roadside or vacant plot",
                "Foul odor, fly breeding, and public hygiene nuisance",
            ],
            "action": "Deploy sanitation vehicle and clearance crew to clear waste spot and spray disinfectant.",
        },
        "Drain/sewage overflow": {
            "severity": 4,
            "reasons": [
                "Sewage effluent overflowing from blocked drain onto public street",
                "Severe sanitation hazard and vector-borne illness contamination risk",
            ],
            "action": "Deploy super-sucker or jetting machine to clear sewer line blockage and apply lime/bleaching.",
        },
        "Dust or smoke": {
            "severity": 2,
            "reasons": [
                "Elevated dust or smoke particulate reported in residential area",
                "Local ambient air quality reduction and pedestrian discomfort",
            ],
            "action": "Inspect emission source and enforce municipal dust suppression measures.",
        },
        "default": {
            "severity": 2,
            "reasons": [
                "Sanitation concern logged for municipal health officer review",
                "General neighborhood cleanliness check required",
            ],
            "action": "Tumakuru City Corporation Sanitation Wing to conduct ground inspection.",
        },
    },
    "water": {
        "Burst pipe": {
            "severity": 5,
            "reasons": [
                "Pressurized municipal water supply pipeline rupture",
                "Massive potable water wastage and active road flooding",
            ],
            "action": "Immediately close distribution isolating valve and dispatch pipe repair crew.",
        },
        "Pipe leakage": {
            "severity": 3,
            "reasons": [
                "Continuous potable water leakage from municipal distribution line",
                "Loss of treated drinking water and gradual road foundation weakening",
            ],
            "action": "Excavate leak spot and install pipe repair collar or replace section.",
        },
        "No water supply": {
            "severity": 3,
            "reasons": [
                "Interruption in scheduled piped drinking water distribution",
                "Domestic water deficit for affected residents",
            ],
            "action": "Inspect feeder main valves and verify booster pump station pressure.",
        },
        "Dirty water": {
            "severity": 4,
            "reasons": [
                "Discolored, turbid, or contaminated drinking water supplied to taps",
                "Significant risk of waterborne illnesses and contamination ingress",
            ],
            "action": "Flush supply distribution line, collect water samples for lab testing, and check for cross-connections.",
        },
        "default": {
            "severity": 2,
            "reasons": [
                "Water utility grievance logged for hydraulic review",
                "Routine water distribution network maintenance required",
            ],
            "action": "Tumakuru City Corporation Water Supply Wing to inspect line and supply pressure.",
        },
    },
}


# -----------------------------------------------------------------------------
# Fallback and Sanitization Helpers
# -----------------------------------------------------------------------------

def get_rule_based_fallback(
    category: str,
    issue_type: str,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a deterministic rule-based triage response when AI is unavailable.
    """
    cat_key = (category or "road").strip().lower()
    if cat_key not in RULE_BASED_FALLBACKS:
        cat_key = "road"

    cat_catalog = RULE_BASED_FALLBACKS[cat_key]
    issue_clean = (issue_type or "").strip()

    # Match issue type or use default
    rule = cat_catalog.get(issue_clean) or cat_catalog["default"]

    issue_label = issue_clean if issue_clean else "Reported issue"
    desc_part = f": {description.strip()}" if description and description.strip() else ""
    summary = (
        f"Citizen reported {issue_label.lower()} in Tumakuru under {cat_key} category{desc_part}. "
        f"Requires on-site verification by municipal field personnel."
    )

    # Ensure summary is at most 2 sentences
    sentences = [s.strip() for s in summary.split(".") if s.strip()]
    trimmed_summary = ". ".join(sentences[:2])
    if trimmed_summary and not trimmed_summary.endswith("."):
        trimmed_summary += "."

    return {
        "detected_issue": issue_label,
        "image_matches_report": True,
        "severity": rule["severity"],
        "severity_reasons": list(rule["reasons"]),
        "summary": trimmed_summary,
        "suggested_action": rule["action"],
        "recommended_department_type": cat_key,
        "confidence": 0.75,
        "ai_source": "fallback",
        "transcription": None,
        "original_language": None,
    }


def _sanitize_result(raw_dict: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely validate and sanitize all fields to guarantee strict schema adherence.
    """
    # detected_issue
    detected = raw_dict.get("detected_issue")
    detected_issue = str(detected).strip() if detected else fallback["detected_issue"]

    # image_matches_report
    matches = raw_dict.get("image_matches_report")
    image_matches_report = bool(matches) if matches is not None else fallback["image_matches_report"]

    # severity: 1 to 5
    try:
        sev = int(raw_dict.get("severity", fallback["severity"]))
        severity = max(1, min(5, sev))
    except (ValueError, TypeError):
        severity = fallback["severity"]

    # severity_reasons: list of 2 to 4 short strings
    reasons = raw_dict.get("severity_reasons")
    clean_reasons: List[str] = []
    if isinstance(reasons, list):
        clean_reasons = [str(r).strip() for r in reasons if str(r).strip()]
    if len(clean_reasons) < 2:
        for r in fallback["severity_reasons"]:
            if r not in clean_reasons:
                clean_reasons.append(r)
            if len(clean_reasons) >= 2:
                break
    clean_reasons = clean_reasons[:4]

    # summary: max 2 sentences
    raw_summary = str(raw_dict.get("summary") or fallback["summary"]).strip()
    sentences = [s.strip() for s in raw_summary.split(".") if s.strip()]
    summary = ". ".join(sentences[:2])
    if summary and not summary.endswith("."):
        summary += "."

    # suggested_action
    action = raw_dict.get("suggested_action")
    suggested_action = str(action).strip() if action else fallback["suggested_action"]

    # recommended_department_type: must be road, pollution, or water
    dept_type = str(raw_dict.get("recommended_department_type", "")).strip().lower()
    if dept_type not in ("road", "pollution", "water"):
        dept_type = fallback["recommended_department_type"]

    # confidence: 0.0 to 1.0
    try:
        conf = float(raw_dict.get("confidence", fallback["confidence"]))
        confidence = round(max(0.0, min(1.0, conf)), 2)
    except (ValueError, TypeError):
        confidence = fallback["confidence"]

    # ai_source
    ai_source = str(raw_dict.get("ai_source") or "gemini").strip().lower()
    if ai_source not in ("gemini", "fallback"):
        ai_source = fallback.get("ai_source", "gemini")

    # Audio voice transcription and language
    transcription = raw_dict.get("transcription")
    if transcription:
        transcription = str(transcription).strip() or None
    else:
        transcription = fallback.get("transcription")

    original_language = raw_dict.get("original_language")
    if original_language:
        original_language = str(original_language).strip() or None
    else:
        original_language = fallback.get("original_language")

    return {
        "detected_issue": detected_issue,
        "image_matches_report": image_matches_report,
        "severity": severity,
        "severity_reasons": clean_reasons,
        "summary": summary,
        "suggested_action": suggested_action,
        "recommended_department_type": dept_type,
        "confidence": confidence,
        "ai_source": ai_source,
        "transcription": transcription,
        "original_language": original_language,
    }


def _call_gemini_api(
    api_key: str,
    model_name: str,
    category: str,
    issue_type: str,
    description: Optional[str],
    photo_path: str,
    audio_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Internal helper to call Gemini API via google-genai SDK with structured output.
    Supports multimodal input (photo + voice recording in Kannada/Hindi/English).
    """
    from google import genai
    from google.genai import types

    # Initialize client with timeout configured in milliseconds
    timeout_ms = int(API_TIMEOUT_SECONDS * 1000)
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )

    # Resolve photo path
    if not os.path.isabs(photo_path):
        resolved_path = os.path.abspath(photo_path)
    else:
        resolved_path = photo_path

    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"Complaint photo not found at path: {photo_path}")

    with open(resolved_path, "rb") as f:
        img_bytes = f.read()

    if not img_bytes:
        raise ValueError("Complaint photo file is empty (0 bytes).")

    # Determine image MIME type
    mime_type, _ = mimetypes.guess_type(resolved_path)
    if not mime_type or not mime_type.startswith("image/"):
        ext = os.path.splitext(resolved_path)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        mime_type = mime_map.get(ext, "image/jpeg")

    image_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)

    cat_key = (category or "road").strip().lower()
    system_instruction = CATEGORY_SYSTEM_PROMPTS.get(cat_key, CATEGORY_SYSTEM_PROMPTS["road"])

    contents = [image_part]

    audio_prompt_part = ""
    # Process optional citizen voice recording
    if audio_path:
        resolved_audio = os.path.abspath(audio_path) if not os.path.isabs(audio_path) else audio_path
        if os.path.exists(resolved_audio) and os.path.getsize(resolved_audio) > 0:
            try:
                with open(resolved_audio, "rb") as af:
                    audio_bytes = af.read()

                audio_ext = os.path.splitext(resolved_audio)[1].lower()
                audio_mime_map = {
                    ".webm": "audio/webm",
                    ".wav": "audio/wav",
                    ".mp3": "audio/mp3",
                    ".ogg": "audio/ogg",
                    ".m4a": "audio/m4a",
                    ".aac": "audio/aac",
                }
                audio_mime = audio_mime_map.get(audio_ext, "audio/webm")
                audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime)
                contents.append(audio_part)

                audio_prompt_part = (
                    "\nAUDIO VOICE NOTE INSTRUCTIONS:\n"
                    "- An audio recording from the citizen in Tumakuru is attached.\n"
                    "- The citizen may speak in Kannada, Hindi, or English (or code-switch between them).\n"
                    "- Accurately transcribe their spoken grievance and translate it into clear English.\n"
                    "- Set 'transcription' to this clear English translation.\n"
                    "- Set 'original_language' to the detected language ('Kannada', 'Hindi', 'English', or 'Mixed').\n"
                    "- Factor what they spoke into your assessment of the detected issue and severity.\n"
                )
            except Exception as e:
                logger.warning("Could not read citizen audio recording (%s); proceeding with photo only.", e)

    user_prompt = (
        f"Grievance Report Submission Details:\n"
        f"- Municipal Category: {category}\n"
        f"- Citizen Selected Issue Type: {issue_type}\n"
        f"- Citizen Description: {description.strip() if description and description.strip() else 'None provided'}\n"
        f"{audio_prompt_part}\n"
        f"Analyze the attached grievance photo (and voice recording if attached) and provide structured triage data according to the schema."
    )
    contents.append(user_prompt)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=TriageResult,
        temperature=0.2,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )
    except Exception as exc:
        # Fallback gracefully if audio caused failure: retry with image only!
        if len(contents) > 2:
            logger.warning("Gemini multimodal call with audio failed (%s); retrying with photo only...", exc)
            fallback_prompt = (
                f"Grievance Report Submission Details:\n"
                f"- Municipal Category: {category}\n"
                f"- Citizen Selected Issue Type: {issue_type}\n"
                f"- Citizen Description: {description.strip() if description and description.strip() else 'None provided'}\n\n"
                f"Analyze the attached grievance photo and provide structured triage data."
            )
            response = client.models.generate_content(
                model=model_name,
                contents=[image_part, fallback_prompt],
                config=config,
            )
        else:
            raise exc

    raw_text = response.text or "{}"
    data = json.loads(raw_text)
    return data


# -----------------------------------------------------------------------------
# Public API Function
# -----------------------------------------------------------------------------

def analyze_complaint(
    category: str,
    issue_type: str,
    description: Optional[str] = None,
    photo_path: Optional[str] = None,
    audio_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyze a citizen grievance using Gemini multimodal AI with full fallback protection.
    Accepts both photo and optional citizen voice recording (Kannada/Hindi/English).

    Parameters:
        category: "road", "pollution", or "water"
        issue_type: Specific issue type (e.g. "Pothole", "Burst pipe", "Garbage burning")
        description: Optional citizen text description
        photo_path: Path to the uploaded photo file on disk
        audio_path: Optional path to recorded citizen audio file on disk

    Returns:
        Structured JSON dictionary containing:
        - detected_issue (str)
        - image_matches_report (bool)
        - severity (int: 1-5)
        - severity_reasons (list of 2-4 strings)
        - summary (str: max 2 sentences)
        - suggested_action (str)
        - recommended_department_type (str: 'road', 'pollution', or 'water')
        - confidence (float: 0.0-1.0)
        - transcription (Optional[str]: English translation of audio)
        - original_language (Optional[str])
    """
    fallback = get_rule_based_fallback(category, issue_type, description)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or api_key in ("paste-your-key-here", "your_api_key_here"):
        logger.info("GEMINI_API_KEY missing or unconfigured; using rule-based fallback triage.")
        return fallback

    if not photo_path:
        logger.info("No photo provided for complaint; using rule-based fallback triage.")
        return fallback

    model_name = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL

    try:
        # Enforce 10-second timeout guard
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _call_gemini_api,
                api_key=api_key,
                model_name=model_name,
                category=category,
                issue_type=issue_type,
                description=description,
                photo_path=photo_path,
                audio_path=audio_path,
            )
            raw_data = future.result(timeout=API_TIMEOUT_SECONDS)

        result = _sanitize_result(raw_data, fallback)
        logger.info(
            "Gemini triage successful: %s | Severity: %s | Confidence: %.2f",
            result["detected_issue"],
            result["severity"],
            result["confidence"],
        )
        return result

    except concurrent.futures.TimeoutError:
        logger.warning(
            "Gemini AI triage timed out after %.1f seconds; using rule-based fallback.",
            API_TIMEOUT_SECONDS,
        )
        return fallback
    except Exception as exc:
        # Never log the secret key
        logger.warning(
            "Gemini AI triage failed (%s: %s); using rule-based fallback.",
            exc.__class__.__name__,
            exc,
        )
        return fallback
