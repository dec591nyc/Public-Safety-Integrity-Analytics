# -*- coding: utf-8 -*-
"""ETL Configuration Constants and Seed Data."""

DATASET_ID = "9603"
BASE_URL = "https://statis.moi.gov.tw/micst/webMain.aspx"
BASE_PARAMS = {
    "sys": "220",
    "kind": "21",
    "type": "1",
    "funid": "c0620101",
    "cycle": "41",
    "outmode": "12",
    "utf": "1",
    "compmode": "0",
    "outkind": "3",
    "fldspc": "0,2,4,3,9,3,14,4,22,1,25,4,34,4,40,31,",
    "codspc0": "0,2,3,2,6,1,9,1,12,1,15,17,",
    "rdm": "public-safety-integrity-analytics",
}

CRIME_SEEDS = [
    ("殺人", "01", "Acts leading to death or intending to cause death", 100, 0, 1, 0, 0),
    ("擄人勒贖", "04", "Acts of violence or threatened violence against a person that involve property", 95, 0, 1, 0, 0),
    ("內亂", "09", "Acts against public safety and national security", 90, 0, 0, 0, 0),
    ("強盜搶奪", "04", "Acts of violence or threatened violence against a person that involve property", 80, 0, 1, 0, 0),
    ("妨害性自主罪", "03", "Injurious acts of a sexual nature", 70, 0, 0, 0, 0),
    ("違反貪污治罪條例", "07", "Acts involving fraud, deception or corruption", 35, 0, 0, 0, 0),
    ("恐嚇取財", "04", "Acts of violence or threatened violence against a person that involve property", 30, 0, 0, 0, 0),
    ("瀆職", "07", "Acts involving fraud, deception or corruption", 25, 0, 0, 0, 0),
    ("違反選罷法", "08", "Acts against public order and authority", 15, 0, 0, 0, 0),
    ("傷害", "02", "Acts causing harm or intending to cause harm to the person", 15, 0, 0, 0, 0),
    ("公共危險", "09", "Acts against public safety and national security", 12, 0, 0, 0, 0),
    ("違反毒品危害防制條例", "06", "Acts involving controlled substances or other psychoactive substances", 12, 0, 0, 0, 0),
    ("駕駛過失", "02", "Acts causing harm or intending to cause harm to the person", 10, 0, 0, 0, 0),
    ("偽造有價證券", "07", "Acts involving fraud, deception or corruption", 10, 0, 0, 0, 0),
    ("妨害風化", "03", "Injurious acts of a sexual nature", 10, 0, 0, 0, 0),
    ("妨害公務", "08", "Acts against public order and authority", 10, 0, 0, 0, 0),
    ("詐欺背信", "07", "Acts involving fraud, deception or corruption", 8, 0, 0, 0, 1),
    ("偽造文書印文", "07", "Acts involving fraud, deception or corruption", 8, 0, 0, 0, 0),
    ("妨害電腦使用", "11", "Other criminal acts not elsewhere classified", 8, 1, 0, 0, 0),
    ("妨害秩序", "08", "Acts against public order and authority", 8, 0, 0, 0, 0),
    ("違反藥事法", "06", "Acts involving controlled substances or other psychoactive substances", 8, 0, 0, 0, 0),
    ("侵占", "05", "Acts against property only", 6, 0, 0, 0, 0),
    ("竊盜", "05", "Acts against property only", 5, 0, 0, 0, 0),
    ("竊佔", "05", "Acts against property only", 5, 0, 0, 0, 0),
    ("重利", "05", "Acts against property only", 5, 0, 0, 0, 0),
    ("妨害家庭及婚姻", "11", "Other criminal acts not elsewhere classified", 5, 0, 0, 1, 0),
    ("違反森林法", "10", "Acts against the natural environment", 5, 0, 0, 0, 0),
    ("毀棄損壞", "05", "Acts against property only", 4, 0, 0, 0, 0),
    ("違反著作權法", "11", "Other criminal acts not elsewhere classified", 4, 0, 0, 0, 0),
    ("贓物", "05", "Acts against property only", 3, 0, 0, 0, 0),
    ("違反專利法", "11", "Other criminal acts not elsewhere classified", 3, 0, 0, 0, 0),
    ("違反商標法", "11", "Other criminal acts not elsewhere classified", 3, 0, 0, 0, 0)
]

CATEGORIES = [
    "fraud",
    "money_laundering",
    "sexual_offense",
    "injury",
    "traffic_injury",
    "public_integrity",
    "election_law",
]

CATEGORY_LABELS = {
    "fraud": "詐欺／詐騙",
    "money_laundering": "洗錢",
    "sexual_offense": "妨害性自主／性侵",
    "injury": "傷害／重傷",
    "traffic_injury": "交通傷害",
    "public_integrity": "貪污／瀆職／圖利／賄賂",
    "election_law": "選罷法／賄選",
}

DOMAIN_LABELS = {
    "civil": "民事",
    "criminal": "刑事",
    "administrative": "行政",
    "constitutional": "憲法",
    "disciplinary": "懲戒",
    "other": "其他",
    "unknown": "未分類",
}

OPINION_SOURCES = [
    {"name": "PTT", "status": "ready"},
    {"name": "Dcard", "status": "ready"},
    {"name": "新聞媒體", "status": "ready"},
    {"name": "法律／司改評論", "status": "ready"},
]

OFFICIAL_CATEGORY_MAP = [
    ("fraud", "詐欺背信", ("詐欺背信",)),
    ("injury", "傷害", ("傷害",)),
    ("sexual_offense", "妨害性自主罪", ("妨害性自主罪",)),
    ("public_integrity", "貪污／瀆職", ("違反貪污治罪條例", "瀆職")),
    ("election_law", "違反選罷法", ("違反選罷法",)),
]

TOTAL_GEOGRAPHY = "機關別總計"
TOTAL_METRIC = "總計"
EXCLUDED_GEOGRAPHIES = {TOTAL_GEOGRAPHY, "署所屬機關"}

OTHER_SEGMENT_COLOR = "#94a3b8"
PEAK_SEGMENT_LIMIT = 10
TOPIC_COLORS = ["#2563eb", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#64748b"]

OFFICIAL_TOPIC_GROUPS = [
    {
        "id": "property_fraud",
        "label": "財產與詐欺",
        "description": "以詐欺、竊盜、侵占、強盜搶奪等民眾最常感受到的財產侵害案件為主。",
        "metrics": ("詐欺背信", "竊盜", "侵占", "竊佔", "毀棄損壞", "強盜搶奪", "恐嚇取財"),
    },
    {
        "id": "violence_personal",
        "label": "暴力與人身安全",
        "description": "觀察殺人、傷害、妨害自由、強盜搶奪等直接影響人身安全的案件。",
        "metrics": ("傷害", "殺人", "妨害自由", "強盜搶奪", "擄人勒贖", "恐嚇取財"),
    },
    {
        "id": "sexual_safety",
        "label": "性犯罪與家庭",
        "description": "聚焦妨害性自主、妨害風化、家庭與婚姻相關案件，適合後續接被害保護與通報資源。",
        "metrics": ("妨害性自主罪", "妨害風化", "妨害家庭及婚姻", "遺棄"),
    },
    {
        "id": "drug_public_safety",
        "label": "毒品與公共安全",
        "description": "比較毒品、公共危險、槍砲彈藥刀械與秩序類案件的縣市分布。",
        "metrics": ("違反毒品危害防制條例", "公共危險", "違反槍砲彈藥刀械管制條例", "妨害秩序"),
    },
    {
        "id": "integrity_governance",
        "label": "廉政與治理",
        "description": "追蹤貪污治罪條例、瀆職、選罷法與偽造文書印文等治理信任相關案件。",
        "metrics": ("違反貪污治罪條例", "瀆職", "違反選罷法", "偽造文書印文"),
    },
    {
        "id": "digital_ip",
        "label": "數位與智慧財產",
        "description": "整理妨害電腦使用、著作權、商標與專利法案件，作為數位犯罪與智財風險入口。",
        "metrics": ("妨害電腦使用", "違反著作權法", "違反商標法", "違反專利法"),
    },
]
