from app.services.processing import _extract_name, _extract_price, _validate_image


def test_extract_price_rupee_symbol():
    assert _extract_price("Red shirt ₹450") == 450.0


def test_extract_price_rs():
    assert _extract_price("Jacket Rs. 1,200") == 1200.0


def test_extract_price_slash():
    assert _extract_price("Saree 850/-") == 850.0


def test_extract_price_none():
    assert _extract_price("No price here") is None


def test_extract_name_strips_price():
    name = _extract_name("Cotton Shirt ₹450")
    assert "450" not in name
    assert "Cotton Shirt" in name


def test_validate_image_jpeg():
    jpeg_magic = b"\xff\xd8\xff" + b"\x00" * 10
    assert _validate_image(jpeg_magic) is True


def test_validate_image_invalid():
    assert _validate_image(b"not an image") is False
