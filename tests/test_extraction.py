import pytest
from app.services.structured_extraction import extract_id_fields
from app.services.extraction.validation import validate_egyptian_national_id, parse_and_validate_date

def test_valid_egyptian_id():
    text = "Egyptian National ID\n29501011234567\nEgypt\nCairo\n2025-01-15"
    result = extract_id_fields(text)
    
    assert result["national_id"] == "29501011234567"
    assert result["birth_date"] == "1995-01-01"
    assert result["governorate_code"] == "12"
    assert result["gender"] == "Female"
    
def test_invalid_partial_id():
    # 10 digits
    text = "Some ID 1212198010"
    result = extract_id_fields(text)
    assert result["national_id"] is None
    
    # 14 digits, but invalid month (15)
    text = "Some ID 29515011234567"
    result = extract_id_fields(text)
    assert result["national_id"] is None
    
def test_arabic_card_positional_name():
    text = "جمهوذتنف خنالع بينا\nبطاقة\nتحقيق\nالشخصية\nأحمد\nمحمد علي إبراهيم\n١٥ شارع السلام المعادي\nقسم المعادي\nالقاهرة"
    result = extract_id_fields(text)
    
    assert result["name"] == "أحمد محمد علي إبراهيم"
    
def test_arabic_card_address_keywords():
    text = "بطاقة\nتحقيق\nالشخصية\nنسرين\nمحمود\nميت\nعنتر\nمركز طلخا\nالدقهلية"
    result = extract_id_fields(text)
    
    assert result["name"] == "نسرين محمود"
    assert result["address"] == "ميت عنتر مركز طلخا الدقهلية"
    
def test_english_id():
    text = "Name: John Doe\nAddress: 123 Main St\nDOB: 12/05/1990"
    result = extract_id_fields(text)
    
    assert result["name"] == "John Doe"
    assert result["address"] == "123 Main St"
    assert result["birth_date"] == "12/05/1990"

def test_missing_fields():
    text = "Just some random text with no fields"
    result = extract_id_fields(text)
    
    assert result["national_id"] is None
    assert result["name"] is None
    assert result["address"] is None
    assert result["birth_date"] is None


def test_unicode_digits_are_normalized_for_id_and_date_validation():
    valid, info, _ = validate_egyptian_national_id("٢٩٥٠١٠١١٢٣٤٥٦٧")
    assert valid is True
    assert info["birth_date"] == "1995-01-01"
    date_valid, parsed, _ = parse_and_validate_date("١٥/٠٥/٢٠٢٤")
    assert date_valid is True
    assert parsed.isoformat() == "2024-05-15"
