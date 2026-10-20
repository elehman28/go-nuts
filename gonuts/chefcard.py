"""The allergy chef card: a short, clear note a diner can show or hand to restaurant staff.

Built from the diner's profile with plain code (no AI), so the wording is the same every time.
Translations are fixed text written once (not generated per request). They were written carefully
but not by native speakers, so the app suggests having a fluent speaker check them. The card never
contains the diner's name or any other personal detail (safety rule 3).
"""
from html import escape

TREE_NUTS = ["Almonds", "Brazil nuts", "Cashews", "Hazelnuts", "Macadamias", "Pecans", "Pine nuts", "Pistachios",
             "Walnuts"]

# language code -> (name shown in the picker, writing direction)
LANGUAGES = {"en": ("English", "ltr"), "es": ("Español", "ltr"), "fr": ("Français", "ltr"),
             "pt": ("Português", "ltr"), "zh": ("中文", "ltr"), "ar": ("العربية", "rtl")}

# profile option -> name in each language
NAMES = {
    "Peanuts":     {"en": "peanuts", "es": "cacahuates (maní)", "fr": "arachides (cacahuètes)", "pt": "amendoim",
                    "zh": "花生", "ar": "الفول السوداني"},
    "Almonds":     {"en": "almonds", "es": "almendras", "fr": "amandes", "pt": "amêndoas", "zh": "杏仁（扁桃仁）",
                    "ar": "اللوز"},
    "Brazil nuts": {"en": "Brazil nuts", "es": "nueces de Brasil", "fr": "noix du Brésil", "pt": "castanhas-do-pará",
                    "zh": "巴西坚果", "ar": "الجوز البرازيلي"},
    "Cashews":     {"en": "cashews", "es": "anacardos o nueces de la India", "fr": "noix de cajou",
                    "pt": "castanhas de caju", "zh": "腰果", "ar": "الكاجو"},
    "Hazelnuts":   {"en": "hazelnuts", "es": "avellanas", "fr": "noisettes", "pt": "avelãs", "zh": "榛子",
                    "ar": "البندق"},
    "Macadamias":  {"en": "macadamias", "es": "nueces de macadamia", "fr": "noix de macadamia", "pt": "macadâmias",
                    "zh": "夏威夷果（澳洲坚果）", "ar": "المكاديميا"},
    "Pecans":      {"en": "pecans", "es": "nueces pecanas", "fr": "noix de pécan", "pt": "nozes-pecã",
                    "zh": "碧根果（美国山核桃）", "ar": "البيكان"},
    "Pine nuts":   {"en": "pine nuts", "es": "piñones", "fr": "pignons de pin", "pt": "pinhões", "zh": "松子",
                    "ar": "الصنوبر"},
    "Pistachios":  {"en": "pistachios", "es": "pistachos", "fr": "pistaches", "pt": "pistaches", "zh": "开心果",
                    "ar": "الفستق الحلبي"},
    "Walnuts":     {"en": "walnuts", "es": "nueces", "fr": "noix", "pt": "nozes", "zh": "核桃",
                    "ar": "عين الجمل (الجوز)"},
    "Coconut":     {"en": "coconut", "es": "coco", "fr": "noix de coco", "pt": "coco", "zh": "椰子", "ar": "جوز الهند"},
}

# Which nuts each tree-nut example (in TEXT[...]["tree_examples"] order) is usually made with.
EXAMPLE_NUTS = [
    {"Pine nuts", "Cashews", "Walnuts", "Almonds", "Pistachios"},   # pesto
    {"Hazelnuts", "Pecans", "Almonds"},                              # praline
    {"Almonds"},                                                     # marzipan
    {"Almonds", "Hazelnuts", "Pistachios", "Walnuts"},               # nougat
    {"Walnuts", "Pistachios"},                                       # baklava
    {"Cashews"},                                                     # cashew-based vegan cheese
]

TEXT = {
    "en": {
        "title": "Food allergy",
        "allergy": {"severe": "I have a severe food allergy to {items}.", "other": "I have a food allergy to {items}."},
        "all_tree": "all tree nuts ({items})",
        "avoid": "Please make sure my food contains none of these, including oils, butters, flours, milks, sauces "
                 "and garnishes made from them{examples}.",
        "examples": " (for example {items})",
        "peanut_examples": ["peanut sauce", "satay", "peanut oil"],
        "tree_examples": ["pesto", "praline", "marzipan", "nougat", "baklava", "cashew-based vegan cheese"],
        "cross": "Please also avoid cross-contact: clean utensils, cutting boards and pans, and no fryer oil shared "
                 "with foods that contain nuts.",
        "severe": "Even a small amount can cause a serious reaction (anaphylaxis). I carry epinephrine.",
        "thanks": "If you're not sure about an ingredient, please let me know. Thank you!",
        "sep": ", ", "and": " and ",
    },
    "es": {
        "title": "Alergia alimentaria",
        "allergy": {"severe": "Tengo una alergia alimentaria grave a {items}.",
                    "other": "Tengo una alergia alimentaria a {items}."},
        "all_tree": "todos los frutos secos de árbol ({items})",
        "avoid": "Por favor, asegúrese de que mi comida no contenga ninguno de estos ingredientes, incluidos aceites, "
                 "mantequillas, harinas, leches, salsas y adornos hechos con ellos{examples}.",
        "examples": " (por ejemplo: {items})",
        "peanut_examples": ["salsa de cacahuate", "satay", "aceite de cacahuate"],
        "tree_examples": ["pesto", "praliné", "mazapán", "turrón", "baklava", "queso vegano de anacardo"],
        "cross": "Por favor, evite también la contaminación cruzada: utensilios, tablas de cortar y sartenes limpios, "
                 "y sin aceite de freír compartido con alimentos que contengan frutos secos.",
        "severe": "Incluso una pequeña cantidad puede causar una reacción grave (anafilaxia). Llevo epinefrina.",
        "thanks": "Si no está seguro de algún ingrediente, por favor avíseme. ¡Gracias!",
        "sep": ", ", "and": " y ",
    },
    "fr": {
        "title": "Allergie alimentaire",
        "allergy": {"severe": "J'ai une allergie alimentaire sévère : {items}.",
                    "other": "J'ai une allergie alimentaire : {items}."},
        "all_tree": "tous les fruits à coque ({items})",
        "avoid": "Merci de vous assurer que mon plat n'en contient aucun, y compris les huiles, beurres, farines, laits, "
                 "sauces et garnitures qui en sont faits{examples}.",
        "examples": " (par exemple : {items})",
        "peanut_examples": ["sauce aux arachides", "satay", "huile d'arachide"],
        "tree_examples": ["pesto", "praliné", "massepain", "nougat", "baklava",
                          "fromage végétalien à base de noix de cajou"],
        "cross": "Merci d'éviter aussi toute contamination croisée : ustensiles, planches à découper et poêles propres, "
                 "et pas d'huile de friture partagée avec des aliments contenant des fruits à coque.",
        "severe": "Même une petite quantité peut provoquer une réaction grave (anaphylaxie). J'ai sur moi de "
                  "l'épinéphrine (adrénaline).",
        "thanks": "Si vous avez un doute sur un ingrédient, merci de me le dire. Merci beaucoup !",
        "sep": ", ", "and": " et ",
    },
    "pt": {
        "title": "Alergia alimentar",
        "allergy": {"severe": "Tenho uma alergia alimentar grave: {items}.",
                    "other": "Tenho uma alergia alimentar: {items}."},
        "all_tree": "todas as castanhas e nozes ({items})",
        "avoid": "Por favor, garanta que minha comida não contenha nenhum desses ingredientes, incluindo óleos, "
                 "manteigas, farinhas, leites, molhos e coberturas feitos com eles{examples}.",
        "examples": " (por exemplo: {items})",
        "peanut_examples": ["molho de amendoim", "satay", "óleo de amendoim"],
        "tree_examples": ["pesto", "praliné", "marzipã", "torrone", "baklava", "queijo vegano de castanha de caju"],
        "cross": "Por favor, evite também a contaminação cruzada: utensílios, tábuas de corte e panelas limpos, e sem "
                 "óleo de fritura compartilhado com alimentos que contenham castanhas ou nozes.",
        "severe": "Mesmo uma pequena quantidade pode causar uma reação grave (anafilaxia). Eu carrego epinefrina "
                  "(adrenalina).",
        "thanks": "Se não tiver certeza sobre algum ingrediente, por favor me avise. Obrigado(a)!",
        "sep": ", ", "and": " e ",
    },
    "zh": {
        "title": "食物过敏",
        "allergy": {"severe": "我对以下食物严重过敏：{items}。", "other": "我对以下食物过敏：{items}。"},
        "all_tree": "所有树坚果（{items}）",
        "avoid": "请确保我的食物中不含以上任何一种，包括用它们制成的油、酱、粉、奶、调味汁和装饰{examples}。",
        "examples": "（例如：{items}）",
        "peanut_examples": ["花生酱汁", "沙爹酱", "花生油"],
        "tree_examples": ["青酱（罗勒松子酱）", "果仁糖", "杏仁膏", "牛轧糖", "果仁蜜饼", "用腰果制作的纯素奶酪"],
        "cross": "也请避免交叉污染：请使用干净的餐具、砧板和锅，不要使用与含坚果食物共用的炸油。",
        "severe": "即使少量也可能引起严重的过敏反应（过敏性休克）。我随身携带肾上腺素。",
        "thanks": "如果您不确定某种配料，请告诉我。谢谢！",
        "sep": "、", "and": "和",
    },
    "ar": {
        "title": "حساسية من الطعام",
        "allergy": {"severe": "لدي حساسية شديدة من الأطعمة التالية: {items}.",
                    "other": "لدي حساسية من الأطعمة التالية: {items}."},
        "all_tree": "جميع المكسرات الشجرية ({items})",
        "avoid": "أرجو التأكد من أن طعامي لا يحتوي على أي منها، بما في ذلك الزيوت والزبدة والدقيق والحليب والصلصات "
                 "والإضافات المصنوعة منها{examples}.",
        "examples": " (مثل: {items})",
        "peanut_examples": ["صلصة الفول السوداني", "الساتيه", "زيت الفول السوداني"],
        "tree_examples": ["البيستو", "البرالين", "المرزبانية", "النوغا", "البقلاوة", "الجبن النباتي المصنوع من الكاجو"],
        "cross": "أرجو أيضًا تجنب التلوث الخلطي: استخدام أدوات وألواح تقطيع وأوانٍ نظيفة، وعدم استخدام زيت قلي مشترك "
                 "مع أطعمة تحتوي على مكسرات.",
        "severe": "حتى الكمية الصغيرة قد تسبب رد فعل خطيرًا (صدمة تأقية). أحمل معي حقنة إبينفرين.",
        "thanks": "إذا لم تكن متأكدًا من أي مكوّن، فأرجو إخباري. شكرًا لك!",
        "sep": "، ", "and": " و",
    },
}


def _join(items: list[str], t: dict) -> str:
    if len(items) <= 1:
        return "".join(items)
    return t["sep"].join(items[:-1]) + t["and"] + items[-1]


def card_lines(profile: dict, lang: str = "en") -> dict:
    """The card's wording for this profile: {"title", "lines": [...], "dir": "ltr"|"rtl"}."""
    t = TEXT[lang]
    chosen = list(profile.get("allergens") or [])
    parts = []
    if "Peanuts" in chosen:
        parts.append(NAMES["Peanuts"][lang])
    if "All tree nuts" in chosen:
        parts.append(t["all_tree"].format(items=t["sep"].join(NAMES[n][lang] for n in TREE_NUTS)))
    else:
        parts += [NAMES[n][lang] for n in TREE_NUTS if n in chosen]
    if "Coconut" in chosen:
        parts.append(NAMES["Coconut"][lang])
    severe = str(profile.get("severity", "")).startswith("Severe")
    lines = [t["allergy"]["severe" if severe else "other"].format(items=_join(parts, t))]

    examples = []
    if "Peanuts" in chosen:
        examples += t["peanut_examples"]
    tree = set(TREE_NUTS) if "All tree nuts" in chosen else set(chosen)
    # Each example only if it's typically made with one of the diner's nuts (marzipan is almond, etc.).
    examples += [ex for ex, nuts in zip(t["tree_examples"], EXAMPLE_NUTS) if tree & nuts]
    lines.append(t["avoid"].format(examples=t["examples"].format(items=t["sep"].join(examples)) if examples else ""))
    lines.append(t["cross"])
    if severe:
        lines.append(t["severe"])
    lines.append(t["thanks"])
    return {"title": t["title"], "lines": lines, "dir": LANGUAGES[lang][1]}


def card_html(profile: dict, lang: str = "en") -> str:
    """The card as an HTML block for the app (styled by theme.CSS classes)."""
    c = card_lines(profile, lang)
    body = "".join(f"<p>{escape(line)}</p>" for line in c["lines"])
    return (f"<div class='gn-chefcard' dir='{c['dir']}' lang='{lang}'>"
            f"<div class='gn-chefcard-title'>{escape(c['title'])}</div>{body}</div>")


def printable_html(profile: dict, lang: str = "es") -> str:
    """A self-contained page with the card in English and one other language, ready to print or save."""
    langs = ["en"] + ([lang] if lang != "en" else [])
    cards = "".join(
        f"<section dir='{c['dir']}' lang='{code}'><h1>{escape(c['title'])}</h1>"
        + "".join(f"<p>{escape(x)}</p>" for x in c["lines"]) + "</section>"
        for code, c in ((code, card_lines(profile, code)) for code in langs))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Food allergy card</title>
<style>
  body {{ font: 17px/1.55 Georgia, "Times New Roman", "Noto Serif", "Noto Sans SC", "Noto Naskh Arabic", serif;
         color: #2b221c; margin: 2rem; }}
  section {{ border: 2px solid #7a4b25; border-radius: 6px; padding: 1.4rem 1.6rem; margin: 0 auto 1.4rem;
            max-width: 34rem; page-break-inside: avoid; }}
  section[dir="rtl"] {{ text-align: right; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 .6rem; color: #7a4b25; letter-spacing: .02em; }}
  p {{ margin: .45rem 0; }}
  footer {{ max-width: 34rem; margin: 0 auto; font: 12px Arial, sans-serif; color: #7d6e62; }}
</style></head><body>{cards}
<footer>Made with Go Nuts. This card is a request to staff, not a guarantee. Always confirm ingredients.
Translations were written carefully but not by native speakers; if you can, ask a fluent speaker to check.</footer>
</body></html>"""
