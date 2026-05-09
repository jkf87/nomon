from openclaw_nomon import verifier


def test_check_font_size_requires_detected_sizes_to_meet_minimum():
    assert verifier.check_font_size('<p style="font-size: 24pt">Large</p>')
    assert verifier.check_font_size('<p style="font-size: 32px">Large</p>')
    assert not verifier.check_font_size('<p style="font-size: 18pt">Small</p>')
    assert not verifier.check_font_size("<p>No declared size</p>")


def test_check_wcag_contrast_supports_aa_and_aaa_thresholds():
    assert verifier.check_wcag_contrast("#000000", "#ffffff")
    assert verifier.check_wcag_contrast("#000", "#fff", level="AAA")
    assert not verifier.check_wcag_contrast("#777777", "#ffffff", level="AAA")
    assert not verifier.check_wcag_contrast("not-a-color", "#ffffff")


def test_check_image_alt_requires_non_empty_alt_on_all_images():
    assert verifier.check_image_alt('<img src="hero.png" alt="Hero image">')
    assert verifier.check_image_alt("<p>No image</p>")
    assert not verifier.check_image_alt('<img src="hero.png">')
    assert not verifier.check_image_alt('<img src="hero.png" alt="">')


def test_check_text_length_compares_character_count():
    assert verifier.check_text_length("abc", 3)
    assert not verifier.check_text_length("abcd", 3)


def test_check_link_liveness_uses_head_status(monkeypatch):
    class Response:
        status_code = 204

    def fake_head(url, allow_redirects, timeout):
        assert url == "https://example.com"
        assert allow_redirects is True
        assert timeout == 5
        return Response()

    monkeypatch.setattr(verifier.requests, "head", fake_head)

    assert verifier.check_link_liveness("https://example.com")


def test_check_link_liveness_handles_request_errors(monkeypatch):
    def fake_head(url, allow_redirects, timeout):
        raise verifier.requests.RequestException("network unavailable")

    monkeypatch.setattr(verifier.requests, "head", fake_head)

    assert not verifier.check_link_liveness("https://example.com")
