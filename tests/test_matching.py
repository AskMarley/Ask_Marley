from askmarley.services.matching import (
    detect_service,
    detect_service_details,
    find_matching_providers,
    get_outward_code,
    is_valid_uk_postcode,
    normalize_uk_postcode,
)


def test_detect_service_for_leak():
    assert detect_service("I have a leaky pipe in my kitchen") == "emergency-plumber"


def test_outward_code_extraction():
    assert get_outward_code("SW1A 1AA") == "SW1A"


def test_uk_postcode_validation():
    assert is_valid_uk_postcode("SW1A 1AA")
    assert is_valid_uk_postcode("sw1a1aa")
    assert not is_valid_uk_postcode("NOT-A-POSTCODE")


def test_uk_postcode_normalization():
    assert normalize_uk_postcode("sw1a1aa") == "SW1A 1AA"


def test_detect_service_details_has_confidence():
    result = detect_service_details("boiler leak emergency")
    assert result["service_slug"] == "emergency-plumber"
    assert result["confidence"] > 0
    assert isinstance(result["options"], list)


def test_detect_service_details_ambiguous():
    result = detect_service_details("clean and wiring support")
    assert result["service_slug"] is not None
    assert isinstance(result["ambiguous"], bool)


def test_provider_matching_accepts_unspaced_postcode():
    results = find_matching_providers("emergency-plumber", "sw1a1aa")
    assert results


def test_provider_ranking_uses_effective_tier():
    results = find_matching_providers("dog-walker", "N1 1AA")
    assert results
    assert results[0]["effective_tier"] == "basic"
    assert results[0]["marleys_choice"] is False


def test_provider_ranking_prefers_premium():
    results = find_matching_providers("emergency-plumber", "SW1A 2AA")
    assert results
    assert results[0]["tier"] == "premium"


def test_unknown_service_returns_no_detection():
    result = detect_service_details("I need something totally unrelated")
    assert result["service_slug"] is None
    assert result["confidence"] == 0.0


def test_invalid_short_postcode_remains_invalid():
    assert not is_valid_uk_postcode("SW1")


def test_detect_service_for_roof_leak_prefers_roofer():
    result = detect_service_details("I need to fix my roof leak urgently")
    assert result["service_slug"] == "roofer"
    assert result["ambiguous"] is False


def test_detect_service_for_smart_tv_maps_to_electrician():
    result = detect_service_details("need to fix my smart tv")
    assert result["service_slug"] == "electrician"
    assert result["ambiguous"] is False


def test_detect_service_for_television_repair_maps_to_electrician():
    result = detect_service_details("can someone do television repair")
    assert result["service_slug"] == "electrician"
    assert result["confidence"] > 0


def test_provider_matching_for_roofer_postcode():
    results = find_matching_providers("roofer", "SW1A 2AA")
    assert results
    assert results[0]["service_slug"] == "roofer"
