"""Hudud (tuman/shahar) nomlarini bir xil shaklga keltirish.

Har manba nomni o'zicha yozadi:
  Joymee: "Chilonzor tumani", "Chirchiq shahar"
  Uybor:  "Чиланзарский район", "Кибрайский район", "городской посёлок Кибрай"
  Qayoda: "Чиланзарский район, Ташкент", "Чирчик, Ташкентская область"
Market'dagi «Mavze» filtri ishlashi uchun hammasini Joymee uslubidagi o'zbekcha nomga keltiramiz.
"""
from __future__ import annotations

import re

# (kanonik nom, mos keladigan ildizlar — lotin/kirill, kichik harfda). Tartib muhim:
# «O'rtachirchiq»/«Yuqorichirchiq»/«Quyichirchiq» «Chirchiq» dan oldin, «Toshkent tumani» shahar nomidan oldin.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Toshkent viloyati
    ("O'rtachirchiq tumani", ("o'rtachirchiq", "ortachirchiq", "o‘rtachirchiq", "среднечирч", "уртачирч")),
    ("Yuqorichirchiq tumani", ("yuqorichirchiq", "верхнечирч", "юкоричирч")),
    ("Quyichirchiq tumani", ("quyichirchiq", "нижнечирч", "куйичирч")),
    ("Chirchiq shahar", ("chirchiq", "chirchik", "чирчик", "чирчиқ")),
    ("Qibray tumani", ("qibray", "kibray", "кибрай", "қибрай")),
    ("Bo'stonliq tumani", ("bo'stonliq", "bostonliq", "bo‘stonliq", "бостанлык", "бўстонлиқ", "бостонлик", "газалкент", "g'azalkent", "gazalkent")),
    ("Zangiota tumani", ("zangiota", "зангиат", "зангиота")),
    ("Nurafshon shahar", ("nurafshon", "нурафшон")),
    ("Toshkent tumani", ("toshkent tumani", "ташкентский район", "тошкент тумани")),
    ("Yangiyo'l", ("yangiyo'l", "yangiyol", "yangiyo‘l", "янгиюль", "янгиюл", "янгийўл")),
    ("Parkent tumani", ("parkent", "паркент")),
    ("Ohangaron", ("ohangaron", "ахангаран", "оҳангарон")),
    ("Olmaliq shahar", ("olmaliq", "алмалык", "олмалиқ")),
    ("Angren shahar", ("angren", "ангрен")),
    ("Bekobod", ("bekobod", "бекабад")),
    ("Piskent tumani", ("piskent", "пскент")),
    ("Chinoz tumani", ("chinoz", "чиназ")),
    ("Bo'ka tumani", ("bo'ka", "boka", "бука")),
    ("Oqqo'rg'on tumani", ("oqqo'rg'on", "oqqorgon", "аккурган")),
    # Toshkent shahri
    ("Mirzo Ulug'bek tumani", ("mirzo ulug", "mirzo-ulug", "мирзо-улуг", "мирзо улуг")),
    ("Yangi Toshkent tumani", ("yangi toshkent", "yangi-toshkent", "янги ташкент", "новый ташкент")),
    ("Yangihayot tumani", ("yangihayot", "янгихаят", "янгиҳаёт")),
    ("Chilonzor tumani", ("chilonzor", "чиланзар", "чилонзор")),
    ("Yunusobod tumani", ("yunusobod", "юнусабад", "юнусобод")),
    ("Yakkasaroy tumani", ("yakkasaroy", "яккасар")),
    ("Yashnobod tumani", ("yashnobod", "яшнабад", "яшнобод")),
    ("Shayxontohur tumani", ("shayxontohur", "shayxontoxur", "шайхантах", "шайхонтоҳур")),
    ("Olmazor tumani", ("olmazor", "алмазар", "олмазор")),
    ("Sergeli tumani", ("sergeli", "сергел")),
    ("Uchtepa tumani", ("uchtepa", "учтеп")),
    ("Bektemir tumani", ("bektemir", "бектемир")),
    ("Mirobod tumani", ("mirobod", "мирабад", "миробод")),
)

TASHKENT_CITY = frozenset({
    "Mirzo Ulug'bek tumani", "Yangi Toshkent tumani", "Yangihayot tumani", "Chilonzor tumani", "Yunusobod tumani",
    "Yakkasaroy tumani", "Yashnobod tumani", "Shayxontohur tumani", "Olmazor tumani", "Sergeli tumani",
    "Uchtepa tumani", "Bektemir tumani", "Mirobod tumani",
})


def normalize_area(*texts: str | None) -> str | None:
    """Berilgan matnlardan (tuman nomi, shahar, manzil) birinchi tanilgan hududni qaytaradi."""
    for text in texts:
        if not text:
            continue
        t = re.sub(r"\s+", " ", str(text).lower().replace("’", "'").replace("ʻ", "'").replace("`", "'"))
        for name, roots in _RULES:
            if any(r in t for r in roots):
                return name
    return None


def area_or_default(default: str, *texts: str | None) -> str:
    """normalize_area, tanilmasa — default (masalan «Toshkent shahri» yoki «Toshkent viloyati»)."""
    return normalize_area(*texts) or default
