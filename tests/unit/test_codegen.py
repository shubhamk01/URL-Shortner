from agentic_engineer.url_shortener.codegen import generate_code, _ALPHABET


def test_generate_code_has_requested_length():
    assert len(generate_code(10)) == 10


def test_generate_code_uses_only_allowed_alphabet():
    code = generate_code(50)
    assert all(ch in _ALPHABET for ch in code)


def test_generate_code_is_not_trivially_constant():
    codes = {generate_code(7) for _ in range(20)}
    assert len(codes) > 1  # extremely unlikely to collide 20 times in a row
