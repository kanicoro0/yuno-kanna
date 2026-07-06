def looks_sensitive(content: str) -> bool:
    markers = (
        "病気", "医療", "診断", "治療", "薬", "通院", "恋愛", "好きな人",
        "彼氏", "彼女", "家族", "家庭", "両親", "父親", "母親",
    )
    return any(marker in content for marker in markers)
