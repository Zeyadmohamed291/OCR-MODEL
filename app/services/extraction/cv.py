import re
import logging
from typing import Dict, Any, Optional, List
from app.services.extraction.base import BaseExtractor
from app.services.extraction.validation import validate_email, validate_phone

logger = logging.getLogger("ocr_microservice")

class CVExtractor(BaseExtractor):
    """
    Modular Extractor for Resumes and CVs (Curriculum Vitae).
    Extracts candidate name, contact information (email, phone, links, location),
    summary, education, work experience, technical skills, certifications, and languages.
    """

    KNOWN_SKILLS = [
        "python", "javascript", "typescript", "c++", "c#", "java", "php", "ruby", "go", "rust", "scala",
        "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "docker", "kubernetes",
        "aws", "azure", "gcp", "cloud", "react", "angular", "vue", "next.js", "node.js", "fastapi",
        "django", "flask", "spring boot", "machine learning", "deep learning", "nlp", "computer vision",
        "tensorflow", "pytorch", "opencv", "scikit-learn", "git", "linux", "agile", "scrum", "ci/cd",
        "html", "css", "tailwind", "rest api", "graphql", "devops", "microservices",
        "برمجة", "تحليل البيانات", "إدارة المشاريع", "تصميم", "ذكاء اصطناعي"
    ]

    KNOWN_LANGUAGES = [
        "arabic", "english", "french", "german", "spanish", "italian", "russian", "chinese", "japanese",
        "العربية", "الإنجليزية", "الفرنسية", "الألمانية"
    ]

    def extract(
        self,
        text: str,
        layout: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        if not text:
            return fields

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 1. Candidate Name: First non-heading line without contact symbols
        candidate_name: Optional[str] = None
        for l in lines[:4]:
            if "@" not in l and not any(kw in l.lower() for kw in ["curriculum", "resume", "cv", "page", "profile", "contact"]):
                words = l.split()
                if 2 <= len(words) <= 5 and len(l) < 45:
                    candidate_name = l
                    break

        if candidate_name:
            n_conf = self.get_layout_confidence(candidate_name, layout, default=0.94)
            self.set_field(fields, "name", candidate_name, confidence=n_conf, is_valid=True)

        # 2. Contact Information: Email, Phone, Links, Location
        contact_info: Dict[str, Any] = {}

        # Email
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', text)
        if email_match:
            email_val = email_match.group(0)
            is_valid_email, email_note = validate_email(email_val)
            e_conf = self.get_layout_confidence(email_val, layout, default=0.98 if is_valid_email else 0.50)
            self.set_field(fields, "email", email_val, confidence=e_conf, is_valid=is_valid_email, note=email_note)
            contact_info["email"] = email_val

        # Phone
        phone_match = re.search(
            r'(?:\+?20\s?|0020\s?|0)?(?:10|11|12|15)\d{8}\b|\+?[1-9]\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}',
            text
        )
        if phone_match:
            phone_val = phone_match.group(0).strip()
            is_valid_phone, phone_note = validate_phone(phone_val)
            p_conf = self.get_layout_confidence(phone_val, layout, default=0.95 if is_valid_phone else 0.50)
            self.set_field(fields, "phone", phone_val, confidence=p_conf, is_valid=is_valid_phone, note=phone_note)
            contact_info["phone"] = phone_val

        # Links (LinkedIn, GitHub, Portfolio)
        links = re.findall(
            r'(?:https?://)?(?:www\.)?(?:linkedin\.com/in/[A-Za-z0-9_-]+|github\.com/[A-Za-z0-9_-]+|[A-Za-z0-9_-]+\.github\.io)',
            text,
            re.IGNORECASE
        )
        if links:
            unique_links = list(dict.fromkeys(links))
            self.set_field(fields, "links", unique_links, confidence=0.95, is_valid=True)
            contact_info["links"] = unique_links

        # Location
        loc_match = re.search(r'\b(Cairo|Giza|Alexandria|Egypt|القاهرة|الجيزة|الإسكندرية|مصر)\b', text, re.IGNORECASE)
        if loc_match:
            contact_info["location"] = loc_match.group(0)

        if contact_info:
            self.set_field(fields, "contact_information", contact_info, confidence=0.95, is_valid=True)

        # 3. Professional Summary / Profile
        summary_val: Optional[str] = None
        summary_match = re.search(
            r'(?:summary|professional\s*summary|profile|about\s*me|نبذة\s*شخصية|نبذة\s*عني)\s*[:\n]\s*([^\n]+(?:\n[^\n]+){1,3})',
            text,
            re.IGNORECASE
        )
        if summary_match:
            summary_val = summary_match.group(1).strip()
            self.set_field(fields, "summary", summary_val, confidence=0.90, is_valid=True)

        # 4. Education
        edu_matches = re.findall(
            r'(?:Bachelor|Master|PhD|B\.Sc|M\.Sc|BSc|MSc|بكالوريوس|ماجستير|دكتوراه|جامعة|University|Faculty of)[^\n]+',
            text,
            re.IGNORECASE
        )
        if edu_matches:
            clean_edu = [e.strip() for e in edu_matches[:5]]
            self.set_field(fields, "education", clean_edu, confidence=0.92, is_valid=True)

        # 5. Experience / Work History
        exp_section_match = re.search(
            r'(?:experience|work\s*experience|employment\s*history|خبرات\s*العمل|الخبرات\s*المهنية)\s*[:\n]\s*([^\n]+(?:\n[^\n]+){1,6})',
            text,
            re.IGNORECASE
        )
        if exp_section_match:
            exp_lines = [
                l.strip() for l in exp_section_match.group(1).splitlines()
                if l.strip() and not any(kw in l.lower() for kw in ["skills", "education", "certifications", "languages", "مهارات", "تعليم"])
            ]
            if exp_lines:
                self.set_field(fields, "experience", exp_lines[:5], confidence=0.92, is_valid=True)

        if not fields.get("experience"):
            exp_matches = re.findall(
                r'(?:(?:Senior|Lead|Junior|Staff|Principal)?\s*(?:Software\s*Engineer|Developer|Data\s*Scientist|Manager|Consultant|Architect|مهندس|مطور)[^\n]*)',
                text,
                re.IGNORECASE
            )
            if exp_matches:
                clean_exp = [e.strip() for e in exp_matches if not summary_val or e.strip() not in summary_val]
                clean_exp = list(dict.fromkeys(clean_exp))
                if clean_exp:
                    self.set_field(fields, "experience", clean_exp[:5], confidence=0.90, is_valid=True)

        # 6. Skills
        lower = text.lower()
        detected_skills = []
        for skill in self.KNOWN_SKILLS:
            if re.search(r'\b' + re.escape(skill) + r'\b', lower):
                detected_skills.append(skill.title() if len(skill) > 3 else skill.upper())
        if detected_skills:
            self.set_field(fields, "skills", detected_skills, confidence=0.95, is_valid=True)

        # 7. Certifications
        cert_matches = re.findall(
            r'(?:(?:AWS|Azure|Google\s*Cloud|GCP|PMP|Scrum|Cisco|CCNA)\s*Certified[^\n]*|شهادة\s*[^\n]+)',
            text,
            re.IGNORECASE
        )
        if cert_matches:
            clean_certs = list(dict.fromkeys([c.strip() for c in cert_matches[:5]]))
            self.set_field(fields, "certifications", clean_certs, confidence=0.92, is_valid=True)

        # 8. Languages
        detected_langs = []
        for lang in self.KNOWN_LANGUAGES:
            if re.search(r'\b' + re.escape(lang) + r'\b', lower):
                detected_langs.append(lang.title())
        if detected_langs:
            self.set_field(fields, "languages", list(dict.fromkeys(detected_langs)), confidence=0.95, is_valid=True)

        return fields
