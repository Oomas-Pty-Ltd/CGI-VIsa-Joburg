from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# Lazy loading - don't initialize until first use
_analyzer = None
_anonymizer = None

def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
    return _analyzer

def _get_anonymizer():
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = AnonymizerEngine()
    return _anonymizer

def mask_pii(text: str) -> str:
    """Mask PII in text using Microsoft Presidio"""
    try:
        analyzer = _get_analyzer()
        anonymizer = _get_anonymizer()
        
        results = analyzer.analyze(
            text=text,
            language='en',
            entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION", "DATE_TIME"]
        )
        
        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={"DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
                      "PHONE_NUMBER": OperatorConfig("mask", {"masking_char": "*", "chars_to_mask": 8}),
                      "EMAIL_ADDRESS": OperatorConfig("mask", {"masking_char": "*", "chars_to_mask": 6})}
        )
        
        return anonymized.text
    except Exception:
        return text
