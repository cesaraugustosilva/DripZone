import argparse
import hashlib
import json
import os
import shutil
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import gettempdir

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageOps
from sqlalchemy import select, func

from app.config import settings
from app.database import SessionLocal, engine
from app.models import Brand, Category, Product, ProductImage, ProductVariant
from app.schemas.product import ProductCreate, VariantCreate
from app.services.products import create_product
from app.services.upload_storage import ensure_canonical_upload_write_allowed
from app.utils.files import ensure_child_path


PILOT_ALBUM_ID = "231036544"
ONE_SIZE_VALUE = "Único"
DEFAULT_PLAN_PATH = Path(gettempdir()) / "dripzone-batch-01-plan.json"
DEFAULT_RESULT_PATH = Path(gettempdir()) / "dripzone-batch-01-result.json"


BATCH_01_ALBUMS = [
    {
        "album_id": "221346032",
        "brand": "Nike",
        "category": "Conjuntos",
        "type": "Hoodie Zip e Jogger",
        "source_model": "21122701001",
        "source_price": {"top": "¥158", "trousers": "¥128"},
        "sizes": ["M", "L", "XL", "2XL"],
        "size_charts": ["003233.png", "003234.png"],
        "colorways": [
            {"color": "Blue / Black", "slug": "blue-black", "cover": "003242.jpg", "gallery": ["003242.jpg", "003243.jpg", "003278.jpg", "003279.jpg", "003319.jpg", "003320.jpg"]},
            {"color": "Beige / White", "slug": "beige-white", "cover": "003244.jpg", "gallery": ["003244.jpg", "003245.jpg", "003286.jpg", "003287.jpg", "003327.jpg", "003328.jpg"]},
            {"color": "Charcoal", "slug": "charcoal", "cover": "003246.jpg", "gallery": ["003246.jpg", "003247.jpg", "003268.jpg", "003269.jpg", "003313.jpg", "003314.jpg"]},
            {"color": "Grey / Black", "slug": "grey-black", "cover": "003248.jpg", "gallery": ["003248.jpg", "003249.jpg", "003270.jpg", "003271.jpg", "003315.jpg", "003316.jpg"]},
            {"color": "White / Black", "slug": "white-black", "cover": "003250.jpg", "gallery": ["003250.jpg", "003251.jpg", "003272.jpg", "003273.jpg", "003311.jpg", "003312.jpg"]},
            {"color": "Red", "slug": "red", "cover": "003252.jpg", "gallery": ["003252.jpg", "003253.jpg", "003274.jpg", "003275.jpg", "003317.jpg", "003318.jpg"]},
            {"color": "Red / Black", "slug": "red-black", "cover": "003254.jpg", "gallery": ["003254.jpg", "003255.jpg", "003276.jpg", "003277.jpg", "003329.jpg", "003330.jpg"]},
            {"color": "Light Grey", "slug": "light-grey", "cover": "003256.jpg", "gallery": ["003256.jpg", "003257.jpg", "003280.jpg", "003281.jpg", "003323.jpg", "003324.jpg"]},
            {"color": "Lime", "slug": "lime", "cover": "003258.jpg", "gallery": ["003258.jpg", "003259.jpg", "003282.jpg", "003283.jpg", "003321.jpg", "003322.jpg"]},
            {"color": "Taupe", "slug": "taupe", "cover": "003260.jpg", "gallery": ["003260.jpg", "003261.jpg", "003284.jpg", "003285.jpg", "003335.jpg", "003336.jpg"]},
            {"color": "Sky Blue / White", "slug": "sky-blue-white", "cover": "003262.jpg", "gallery": ["003262.jpg", "003263.jpg", "003288.jpg", "003289.jpg", "003325.jpg", "003326.jpg"]},
        ],
    },
    {
        "album_id": "241324214",
        "brand": "Lacoste",
        "category": "Conjuntos",
        "type": "Polo e Shorts",
        "source_model": "3206101820",
        "source_price": {"set": "¥168"},
        "sizes": ["M", "L", "XL", "2XL", "3XL"],
        "size_charts": ["047781.png", "014435.png"],
        "colorways": [
            {"color": "Red", "slug": "red", "cover": "047787.jpg", "gallery": ["047787.jpg", "047789.jpg", "047833.jpg", "047834.jpg"]},
            {"color": "Light Blue", "slug": "light-blue", "cover": "047788.jpg", "gallery": ["047788.jpg", "047791.jpg", "047835.jpg", "047837.jpg"]},
            {"color": "Pink Beige", "slug": "pink-beige", "cover": "047790.jpg", "gallery": ["047790.jpg", "047793.jpg", "047850.jpg", "047852.jpg"]},
            {"color": "Coffee", "slug": "coffee", "cover": "047792.jpg", "gallery": ["047792.jpg", "047794.jpg", "047836.jpg", "047842.jpg"]},
            {"color": "Mint", "slug": "mint", "cover": "047795.jpg", "gallery": ["047795.jpg", "047797.jpg", "047840.jpg", "047841.jpg"]},
            {"color": "Black", "slug": "black", "cover": "047796.jpg", "gallery": ["047796.jpg", "047798.jpg", "047843.jpg", "047844.jpg"]},
            {"color": "Blue", "slug": "blue", "cover": "047799.jpg", "gallery": ["047799.jpg", "047800.jpg", "047838.jpg", "047839.jpg"]},
            {"color": "Beige", "slug": "beige", "cover": "047801.jpg", "gallery": ["047801.jpg", "047802.jpg", "047845.jpg", "047851.jpg"]},
            {"color": "Green", "slug": "green", "cover": "047803.jpg", "gallery": ["047803.jpg", "047804.jpg", "047826.jpg", "047827.jpg", "047855.jpg"]},
            {"color": "Navy", "slug": "navy", "cover": "047805.jpg", "gallery": ["047805.jpg", "047807.jpg", "047846.jpg", "047847.jpg"]},
            {"color": "Charcoal", "slug": "charcoal", "cover": "047806.jpg", "gallery": ["047806.jpg", "047808.jpg", "047828.jpg", "047829.jpg"]},
            {"color": "Grey", "slug": "grey", "cover": "047809.jpg", "gallery": ["047809.jpg", "047811.jpg", "047828.jpg", "047829.jpg"]},
            {"color": "Bright Green", "slug": "bright-green", "cover": "047810.jpg", "gallery": ["047810.jpg", "047812.jpg", "047813.jpg", "047855.jpg"]},
        ],
    },
    {
        "album_id": "244863783",
        "brand": "Bape",
        "category": "Moletons",
        "type": "Shark Hoodie",
        "source_model": "52070715158",
        "source_price": {"hoodie": "¥175"},
        "sizes": ["M", "L", "XL", "2XL", "3XL"],
        "size_charts": ["058057.png"],
        "colorways": [
            {"color": "White Camo", "slug": "white-camo", "cover": "058064.jpg", "gallery": ["058064.jpg", "058065.jpg", "058066.jpg", "058067.jpg", "058068.jpg", "058069.jpg", "058070.jpg", "058071.jpg"]},
            {"color": "Aqua Pink Camo", "slug": "aqua-pink-camo", "cover": "058074.jpg", "gallery": ["058074.jpg", "058075.jpg", "058076.jpg", "058077.jpg", "058078.jpg", "058079.jpg", "058080.jpg", "058081.jpg"]},
            {"color": "Pink Camo", "slug": "pink-camo", "cover": "058083.jpg", "gallery": ["058083.jpg", "058084.jpg", "058085.jpg", "058086.jpg", "058087.jpg", "058088.jpg", "058089.jpg", "058090.jpg"]},
            {"color": "Blue Camo", "slug": "blue-camo", "cover": "058092.jpg", "gallery": ["058092.jpg", "058093.jpg", "058094.jpg", "058095.jpg", "058096.jpg", "058097.jpg", "058098.jpg", "058099.jpg"]},
            {"color": "Green Camo", "slug": "green-camo", "cover": "058101.jpg", "gallery": ["058101.jpg", "058102.jpg", "058103.jpg", "058104.jpg", "058105.jpg", "058106.jpg", "058107.jpg", "058108.jpg"]},
            {"color": "Teal Camo", "slug": "teal-camo", "cover": "058110.jpg", "gallery": ["058110.jpg", "058111.jpg", "058112.jpg", "058113.jpg", "058114.jpg", "058115.jpg", "058116.jpg", "058117.jpg"]},
        ],
    },
]


BATCH_02_ALBUMS = [
    {
        "album_id": "245673728",
        "brand": "Supreme",
        "category": "Conjuntos",
        "type": "Hoodie e Jogger",
        "source_model": "52071521182",
        "source_price": {"top": "￥218", "trousers": "￥188"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["005508.png", "005509.png"],
        "colorways": [
            {"color": "Brown", "slug": "brown", "cover": "005516.jpg", "gallery": ["005516.jpg", "005517.jpg", "005573.jpg", "005574.jpg", "005576.jpg"]},
            {"color": "Red", "slug": "red", "cover": "005518.jpg", "gallery": ["005518.jpg", "005520.jpg", "005521.jpg", "005579.jpg"]},
            {"color": "Khaki", "slug": "khaki", "cover": "005522.jpg", "gallery": ["005522.jpg", "005523.jpg", "005524.jpg"]},
            {"color": "Purple", "slug": "purple", "cover": "005525.jpg", "gallery": ["005525.jpg", "005526.jpg", "005527.jpg", "005570.jpg", "005571.jpg", "005572.jpg"]},
            {"color": "Light Blue", "slug": "light-blue", "cover": "005528.jpg", "gallery": ["005528.jpg", "005529.jpg", "005530.jpg", "005575.jpg", "005577.jpg", "005578.jpg"]},
            {"color": "Grey", "slug": "grey", "cover": "005531.jpg", "gallery": ["005531.jpg", "005532.jpg", "005533.jpg", "005561.jpg", "005562.jpg", "005563.jpg"]},
            {"color": "Black", "slug": "black", "cover": "005534.jpg", "gallery": ["005534.jpg", "005535.jpg", "005536.jpg", "005537.jpg", "005538.jpg", "005539.jpg", "005564.jpg", "005565.jpg", "005566.jpg"]},
            {"color": "Green", "slug": "green", "cover": "005541.jpg", "gallery": ["005541.jpg", "005542.jpg", "005543.jpg"]},
            {"color": "Navy", "slug": "navy", "cover": "005544.jpg", "gallery": ["005544.jpg", "005545.jpg", "005546.jpg"]},
            {"color": "Camo", "slug": "camo", "cover": "005547.jpg", "gallery": ["005547.jpg", "005548.jpg", "005549.jpg", "005567.jpg", "005568.jpg", "005569.jpg"]},
        ],
    },
    {
        "album_id": "246237840",
        "brand": "Adidas",
        "category": "Conjuntos",
        "type": "Jaqueta e Calca",
        "source_model": "3207208819",
        "source_price": {"top": "￥168", "trousers": "￥129"},
        "sizes": ["S", "M", "L", "XL", "2XL"],
        "size_charts": ["001910.png", "001912.png"],
        "colorways": [
            {"color": "Black", "slug": "black", "cover": "001918.jpg", "gallery": ["001918.jpg", "001919.jpg", "001921.jpg", "001961.jpg"]},
            {"color": "White", "slug": "white", "cover": "001920.jpg", "gallery": ["001920.jpg", "001922.jpg"]},
            {"color": "Burgundy", "slug": "burgundy", "cover": "001923.jpg", "gallery": ["001923.jpg", "001927.jpg", "001935.jpg", "001936.jpg", "001962.jpg", "001963.jpg", "001965.jpg", "001966.jpg"]},
            {"color": "Blue", "slug": "blue", "cover": "001924.jpg", "gallery": ["001924.jpg", "001925.jpg", "001933.jpg", "001934.jpg", "001960.jpg", "001964.jpg"]},
            {"color": "Light Blue", "slug": "light-blue", "cover": "001926.jpg", "gallery": ["001926.jpg", "001928.jpg", "001971.jpg", "001972.jpg"]},
            {"color": "Mustard", "slug": "mustard", "cover": "001929.jpg", "gallery": ["001929.jpg", "001930.jpg", "001980.jpg"]},
            {"color": "Charcoal", "slug": "charcoal", "cover": "001931.jpg", "gallery": ["001931.jpg", "001932.jpg", "001973.jpg", "001974.jpg"]},
            {"color": "Mint", "slug": "mint", "cover": "001937.jpg", "gallery": ["001937.jpg", "001938.jpg", "001975.jpg", "001976.jpg"]},
            {"color": "Olive", "slug": "olive", "cover": "001939.jpg", "gallery": ["001939.jpg", "001940.jpg", "001979.jpg", "001981.jpg"]},
            {"color": "Pink", "slug": "pink", "cover": "001941.jpg", "gallery": ["001941.jpg", "001942.jpg", "001977.jpg", "001978.jpg"]},
            {"color": "Orange", "slug": "orange", "cover": "001943.jpg", "gallery": ["001943.jpg", "001944.jpg", "001969.jpg", "001970.jpg"]},
        ],
    },
    {
        "album_id": "223164069",
        "brand": "Fear of God Essentials",
        "category": "Conjuntos",
        "type": "T-Shirt e Shorts",
        "source_model": "3201151417",
        "source_price": {"top": "￥105", "shorts": "￥115"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["014270.png", "014269.png"],
        "colorways": [
            {"color": "Light Grey", "slug": "light-grey", "cover": "014819.jpg", "gallery": ["014819.jpg", "014821.jpg", "014853.jpg", "014854.jpg", "014857.jpg", "014859.jpg"]},
            {"color": "Cream", "slug": "cream", "cover": "014822.jpg", "gallery": ["014822.jpg", "014823.jpg", "014824.jpg", "014855.jpg", "014856.jpg", "014860.jpg", "014862.jpg"]},
            {"color": "Tan", "slug": "tan", "cover": "014825.jpg", "gallery": ["014825.jpg", "014826.jpg", "014827.jpg", "014858.jpg", "014861.jpg", "014863.jpg", "014864.jpg"]},
            {"color": "Grey", "slug": "grey", "cover": "014828.jpg", "gallery": ["014828.jpg", "014829.jpg", "014832.jpg"]},
            {"color": "Charcoal", "slug": "charcoal", "cover": "014832.jpg", "gallery": ["014832.jpg", "014833.jpg"]},
            {"color": "Black", "slug": "black", "cover": "014834.jpg", "gallery": ["014834.jpg", "014835.jpg", "014836.jpg", "014867.jpg", "014868.jpg", "014870.jpg"]},
        ],
    },
    {
        "album_id": "228053806",
        "brand": "Amiri",
        "category": "Conjuntos",
        "type": "T-Shirt e Shorts",
        "source_model": "3203161721",
        "source_price": {"top": "￥158", "shorts": "￥168"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["009168.png", "009169.png"],
        "colorways": [
            {"color": "Olive", "slug": "olive", "cover": "009176.jpg", "gallery": ["009176.jpg", "009177.jpg", "009178.jpg", "009179.jpg", "009203.jpg", "009204.jpg", "009206.jpg", "009207.jpg", "009215.jpg"]},
            {"color": "Green", "slug": "green", "cover": "009182.jpg", "gallery": ["009182.jpg", "009183.jpg", "009184.jpg", "009208.jpg", "009209.jpg"]},
            {"color": "Tan", "slug": "tan", "cover": "009185.jpg", "gallery": ["009185.jpg", "009186.jpg", "009187.jpg", "009210.jpg", "009211.jpg"]},
            {"color": "White", "slug": "white", "cover": "009188.jpg", "gallery": ["009188.jpg", "009189.jpg", "009190.jpg"]},
            {"color": "Black", "slug": "black", "cover": "009229.jpg", "gallery": ["009229.jpg"]},
        ],
    },
    {
        "album_id": "221817131",
        "brand": "Corteiz",
        "category": "Conjuntos",
        "type": "Hoodie e Calca",
        "source_model": "22010307125",
        "source_price": {"top": "￥185", "trousers": "￥168"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["023177.png", "023178.png"],
        "colorways": [
            {"color": "Navy", "slug": "navy", "cover": "023184.jpg", "gallery": ["023184.jpg", "023185.jpg", "023186.jpg", "023218.jpg", "023229.jpg"]},
            {"color": "Grey", "slug": "grey", "cover": "023187.jpg", "gallery": ["023187.jpg", "023188.jpg", "023189.jpg", "023223.jpg", "023224.jpg"]},
            {"color": "Light Blue", "slug": "light-blue", "cover": "023190.jpg", "gallery": ["023190.jpg", "023191.jpg", "023192.jpg", "023221.jpg", "023222.jpg"]},
            {"color": "Brown", "slug": "brown", "cover": "023193.jpg", "gallery": ["023193.jpg", "023194.jpg", "023195.jpg", "023219.jpg", "023220.jpg"]},
            {"color": "Black", "slug": "black", "cover": "023196.jpg", "gallery": ["023196.jpg", "023197.jpg", "023198.jpg", "023199.jpg", "023200.jpg", "023225.jpg", "023226.jpg", "023227.jpg", "023233.jpg"]},
        ],
    },
    {
        "album_id": "223959805",
        "brand": "Gallery Dept",
        "category": "Conjuntos",
        "type": "T-Shirt e Shorts",
        "source_model": "3201232317",
        "source_price": {"top": "￥108", "shorts": "￥128"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["012006.png", "012008.png"],
        "colorways": [
            {"color": "Green Camo", "slug": "green-camo", "cover": "012014.jpg", "gallery": ["012014.jpg", "012015.jpg", "012016.jpg", "012017.jpg", "012038.jpg", "012039.jpg"]},
            {"color": "Sand Camo", "slug": "sand-camo", "cover": "012018.jpg", "gallery": ["012018.jpg", "012019.jpg", "012020.jpg", "012045.jpg", "012046.jpg"]},
            {"color": "Bright Camo", "slug": "bright-camo", "cover": "012021.jpg", "gallery": ["012021.jpg", "012022.jpg", "012023.jpg", "012040.jpg", "012041.jpg"]},
            {"color": "Tiger Camo", "slug": "tiger-camo", "cover": "012024.jpg", "gallery": ["012024.jpg", "012025.jpg", "012026.jpg", "012027.jpg", "012042.jpg", "012043.jpg", "012044.jpg", "012051.jpg"]},
        ],
    },
    {
        "album_id": "243436320",
        "brand": "Stussy",
        "category": "Camisetas",
        "type": "T-Shirt",
        "source_model": "126263002",
        "source_price": {"shirt": "￥82"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["034347.png"],
        "colorways": [
            {"color": "White", "slug": "white", "cover": "049528.jpg", "gallery": ["049528.jpg", "049529.jpg", "049546.jpg", "049547.jpg"]},
            {"color": "White / Light Blue", "slug": "white-light-blue", "cover": "049530.jpg", "gallery": ["049530.jpg", "049531.jpg", "049548.jpg", "049550.jpg"]},
            {"color": "Olive", "slug": "olive", "cover": "049532.jpg", "gallery": ["049532.jpg", "049533.jpg", "049549.jpg", "049552.jpg"]},
            {"color": "Tan", "slug": "tan", "cover": "049534.jpg", "gallery": ["049534.jpg", "049535.jpg", "049551.jpg", "049553.jpg"]},
            {"color": "Charcoal", "slug": "charcoal", "cover": "049536.jpg", "gallery": ["049536.jpg", "049537.jpg", "049554.jpg", "049555.jpg"]},
            {"color": "Navy", "slug": "navy", "cover": "049538.jpg", "gallery": ["049538.jpg", "049539.jpg", "049556.jpg", "049557.jpg"]},
            {"color": "Black", "slug": "black", "cover": "049540.jpg", "gallery": ["049540.jpg", "049541.jpg", "049543.jpg", "049558.jpg", "049559.jpg"]},
        ],
    },
    {
        "album_id": "244223726",
        "brand": "Bape",
        "category": "Camisetas",
        "type": "T-Shirt",
        "source_model": "12710631",
        "source_price": {"shirt": "￥88"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["074969.png"],
        "colorways": [
            {"color": "White / Blue Camo", "slug": "white-blue-camo", "cover": "075547.jpg", "gallery": ["075547.jpg", "075548.jpg", "075549.jpg", "075550.jpg", "075551.jpg"]},
            {"color": "White / Green Camo", "slug": "white-green-camo", "cover": "075552.jpg", "gallery": ["075552.jpg", "075553.jpg", "075554.jpg", "075555.jpg", "075556.jpg", "075557.jpg", "075558.jpg"]},
            {"color": "White / Pink Camo", "slug": "white-pink-camo", "cover": "075559.jpg", "gallery": ["075559.jpg", "075560.jpg", "075561.jpg", "075562.jpg", "075563.jpg"]},
            {"color": "Black / Pink Camo", "slug": "black-pink-camo", "cover": "075564.jpg", "gallery": ["075564.jpg", "075565.jpg", "075568.jpg", "075569.jpg", "075570.jpg", "075571.jpg"]},
            {"color": "Black / Blue Camo", "slug": "black-blue-camo", "cover": "075572.jpg", "gallery": ["075572.jpg", "075573.jpg", "075574.jpg", "075575.jpg", "075576.jpg", "075577.jpg", "075578.jpg"]},
            {"color": "Black / Green Camo", "slug": "black-green-camo", "cover": "075579.jpg", "gallery": ["075579.jpg", "075580.jpg", "075581.jpg", "075582.jpg", "075583.jpg", "075584.jpg", "075585.jpg"]},
        ],
    },
    {
        "album_id": "245309226",
        "brand": "Bape",
        "category": "Shorts",
        "type": "Shorts",
        "source_model": "4207110277",
        "source_price": {"shorts": "￥118"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["103374.png"],
        "colorways": [
            {"color": "Blue Camo", "slug": "blue-camo", "cover": "103357.jpg", "gallery": ["103357.jpg", "103359.jpg", "103360.jpg", "103407.jpg", "103419.jpg", "103421.jpg", "103436.jpg"]},
            {"color": "Green Camo", "slug": "green-camo", "cover": "103313.jpg", "gallery": ["103313.jpg", "103402.jpg", "103408.jpg", "103409.jpg", "103414.jpg", "103415.jpg", "103417.jpg", "103423.jpg", "103445.jpg"]},
            {"color": "Pink Camo", "slug": "pink-camo", "cover": "103405.jpg", "gallery": ["103405.jpg", "103411.jpg", "103424.jpg", "103435.jpg", "103449.jpg", "103453.jpg"]},
            {"color": "Navy Camo", "slug": "navy-camo", "cover": "103412.jpg", "gallery": ["103412.jpg", "103427.jpg", "103432.jpg", "103444.jpg"]},
            {"color": "Red Camo", "slug": "red-camo", "cover": "103429.jpg", "gallery": ["103422.jpg", "103426.jpg", "103429.jpg", "103430.jpg", "103442.jpg", "103446.jpg"]},
            {"color": "Purple Camo", "slug": "purple-camo", "cover": "103410.jpg", "gallery": ["103410.jpg", "103425.jpg", "103428.jpg", "103434.jpg", "103443.jpg", "103452.jpg"]},
        ],
    },
    {
        "album_id": "248604790",
        "brand": "Adidas",
        "category": "Jaquetas",
        "type": "Jaqueta",
        "source_model": "22080608001",
        "source_price": {"jacket": "￥268"},
        "sizes": ["S", "M", "L", "XL", "2XL"],
        "size_charts": ["020048.png"],
        "colorways": [
            {"color": "Pink", "slug": "pink", "cover": "020053.jpg", "gallery": ["020053.jpg", "020054.jpg"]},
            {"color": "Mustard", "slug": "mustard", "cover": "020055.jpg", "gallery": ["020055.jpg", "020056.jpg"]},
            {"color": "Navy", "slug": "navy", "cover": "020057.jpg", "gallery": ["020057.jpg", "020058.jpg"]},
            {"color": "Cream", "slug": "cream", "cover": "020059.jpg", "gallery": ["020059.jpg", "020060.jpg"]},
            {"color": "Light Blue", "slug": "light-blue", "cover": "020061.jpg", "gallery": ["020061.jpg", "020062.jpg"]},
            {"color": "Burgundy", "slug": "burgundy", "cover": "020063.jpg", "gallery": ["020063.jpg", "020064.jpg", "020082.jpg", "020083.jpg"]},
            {"color": "Blue", "slug": "blue", "cover": "020065.jpg", "gallery": ["020065.jpg", "020066.jpg"]},
            {"color": "Mint", "slug": "mint", "cover": "020067.jpg", "gallery": ["020067.jpg", "020068.jpg"]},
            {"color": "Rust", "slug": "rust", "cover": "020069.jpg", "gallery": ["020069.jpg", "020070.jpg"]},
            {"color": "Olive", "slug": "olive", "cover": "020071.jpg", "gallery": ["020071.jpg", "020072.jpg"]},
            {"color": "Brown", "slug": "brown", "cover": "020073.jpg", "gallery": ["020073.jpg", "020074.jpg"]},
            {"color": "Charcoal", "slug": "charcoal", "cover": "020075.jpg", "gallery": ["020075.jpg", "020076.jpg"]},
            {"color": "White", "slug": "white", "cover": "020077.jpg", "gallery": ["020077.jpg", "020078.jpg"]},
            {"color": "Black", "slug": "black", "cover": "020079.jpg", "gallery": ["020079.jpg", "020080.jpg", "020081.jpg", "020088.jpg"]},
        ],
    },
    {
        "album_id": "222064049",
        "brand": "Supreme",
        "category": "Moletons",
        "type": "Hoodie",
        "source_model": "11150235",
        "source_price": {"hoodie": "￥419"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["025742.png"],
        "colorways": [
            {"color": "Pink", "slug": "pink", "cover": "025748.jpg", "gallery": ["025748.jpg", "025749.jpg", "025750.jpg", "025751.jpg", "025752.jpg", "025753.jpg"]},
            {"color": "Blue", "slug": "blue", "cover": "025754.jpg", "gallery": ["025754.jpg", "025755.jpg", "025756.jpg", "025757.jpg", "025758.jpg"]},
            {"color": "Black", "slug": "black", "cover": "025759.jpg", "gallery": ["025759.jpg", "025760.jpg", "025761.jpg", "025762.jpg", "025763.jpg", "025764.jpg", "025765.jpg", "025766.jpg", "025767.jpg", "025768.jpg", "025769.jpg", "025770.jpg"]},
        ],
    },
]


def one_size_album(
    *,
    album_id: str,
    brand: str,
    category: str,
    type: str,
    source_model: str,
    source_price: dict,
    colorways: list[dict],
) -> dict:
    return {
        "album_id": album_id,
        "brand": brand,
        "category": category,
        "type": type,
        "source_model": source_model,
        "source_price": source_price,
        "sizes": [ONE_SIZE_VALUE],
        "size_charts": [],
        "one_size": True,
        "colorways": colorways,
    }


BATCH_03_ALBUMS = [
    one_size_album(
        album_id="248618209",
        brand="Supreme",
        category="Acessórios",
        type="Beanie",
        source_model="32080550182",
        source_price={"hat": "￥105"},
        colorways=[
            {"color": "Navy", "slug": "navy", "cover": "098023.jpg", "gallery": ["098023.jpg", "098099.jpg", "098104.jpg", "098226.jpg", "098246.jpg", "098253.jpg"]},
            {"color": "Grey", "slug": "grey", "cover": "098034.jpg", "gallery": ["098034.jpg", "098074.jpg", "098086.jpg", "098095.jpg", "098201.jpg", "098238.jpg", "098240.jpg"]},
            {"color": "White", "slug": "white", "cover": "098063.jpg", "gallery": ["098063.jpg", "098059.jpg", "098084.jpg", "098089.jpg", "098147.jpg", "098148.jpg", "098153.jpg", "098195.jpg", "098235.jpg", "098250.jpg", "098281.jpg", "098292.jpg"]},
            {"color": "Pink", "slug": "pink", "cover": "098072.jpg", "gallery": ["098072.jpg", "098069.jpg", "098122.jpg", "098168.jpg", "098196.jpg", "098223.jpg", "098267.jpg", "098269.jpg", "098289.jpg"]},
            {"color": "Black", "slug": "black", "cover": "098115.jpg", "gallery": ["098115.jpg", "098119.jpg", "098138.jpg", "098142.jpg", "098172.jpg", "098175.jpg", "098176.jpg", "098206.jpg", "098243.jpg", "098265.jpg", "098274.jpg"]},
            {"color": "Olive", "slug": "olive", "cover": "098210.jpg", "gallery": ["098210.jpg", "098127.jpg", "098156.jpg", "098192.jpg", "098220.jpg"]},
            {"color": "Blue", "slug": "blue", "cover": "098191.jpg", "gallery": ["098191.jpg", "098048.jpg", "098154.jpg", "098202.jpg", "098283.jpg"]},
            {"color": "Red", "slug": "red", "cover": "098262.jpg", "gallery": ["098262.jpg", "098046.jpg", "098278.jpg"]},
        ],
    ),
    one_size_album(
        album_id="243238742",
        brand="Corteiz",
        category="Acessórios",
        type="Boné",
        source_model="126250543",
        source_price={"hat": "￥72"},
        colorways=[
            {"color": "Black", "slug": "black", "cover": "118182.jpg", "gallery": ["118182.jpg", "118183.jpg", "118184.jpg", "118185.jpg", "118186.jpg", "118212.jpg", "118213.jpg", "118227.jpg", "118228.jpg", "118229.jpg", "118230.jpg", "118231.jpg"]},
            {"color": "Navy", "slug": "navy", "cover": "118187.jpg", "gallery": ["118187.jpg", "118188.jpg", "118189.jpg", "118190.jpg", "118191.jpg"]},
            {"color": "Red / White", "slug": "red-white", "cover": "118192.jpg", "gallery": ["118192.jpg", "118193.jpg", "118194.jpg", "118195.jpg", "118196.jpg"]},
            {"color": "Pink", "slug": "pink", "cover": "118197.jpg", "gallery": ["118197.jpg", "118198.jpg", "118199.jpg", "118200.jpg", "118201.jpg"]},
            {"color": "Brown", "slug": "brown", "cover": "118202.jpg", "gallery": ["118202.jpg", "118203.jpg", "118204.jpg", "118205.jpg"]},
            {"color": "White / Black", "slug": "white-black", "cover": "118206.jpg", "gallery": ["118206.jpg", "118208.jpg", "118209.jpg", "118210.jpg", "118211.jpg"]},
            {"color": "Grey", "slug": "grey", "cover": "118214.jpg", "gallery": ["118214.jpg", "118215.jpg", "118216.jpg", "118217.jpg", "118218.jpg", "118219.jpg", "118220.jpg", "118221.jpg"]},
            {"color": "Camo", "slug": "camo", "cover": "118222.jpg", "gallery": ["118222.jpg", "118223.jpg", "118224.jpg", "118225.jpg", "118226.jpg"]},
        ],
    ),
    one_size_album(
        album_id="234743385",
        brand="Supreme",
        category="Acessórios",
        type="Bag",
        source_model="22042541172",
        source_price={"bag": "￥140"},
        colorways=[
            {"color": "Black", "slug": "black", "cover": "039553.jpg", "gallery": ["039553.jpg", "039554.jpg", "039555.jpg", "039556.jpg", "039566.jpg", "039567.jpg", "039568.jpg", "039569.jpg", "039570.jpg", "039571.jpg", "039572.jpg", "039573.jpg"]},
            {"color": "Olive", "slug": "olive", "cover": "039557.jpg", "gallery": ["039557.jpg", "039558.jpg", "039559.jpg"]},
            {"color": "Red", "slug": "red", "cover": "039560.jpg", "gallery": ["039560.jpg", "039561.jpg", "039562.jpg"]},
            {"color": "Leopard", "slug": "leopard", "cover": "039563.jpg", "gallery": ["039563.jpg", "039564.jpg", "039565.jpg"]},
        ],
    ),
    one_size_album(
        album_id="237006793",
        brand="Nike",
        category="Acessórios",
        type="ACG Bag",
        source_model="22051102172",
        source_price={"bag": "￥168"},
        colorways=[
            {"color": "Olive", "slug": "olive", "cover": "138296.jpg", "gallery": ["138296.jpg", "138297.jpg", "138298.jpg", "138300.jpg"]},
            {"color": "Lavender", "slug": "lavender", "cover": "138299.jpg", "gallery": ["138299.jpg", "138301.jpg", "138302.jpg"]},
            {"color": "Teal", "slug": "teal", "cover": "138305.jpg", "gallery": ["138303.jpg", "138305.jpg", "138306.jpg"]},
            {"color": "Mint", "slug": "mint", "cover": "138304.jpg", "gallery": ["138304.jpg", "138307.jpg", "138309.jpg"]},
            {"color": "Black", "slug": "black", "cover": "138310.jpg", "gallery": ["138310.jpg", "138314.jpg", "138315.jpg", "138316.jpg", "138317.jpg", "138318.jpg", "138319.jpg", "138320.jpg", "138321.jpg", "138322.jpg", "138323.jpg", "138324.jpg"]},
            {"color": "White", "slug": "white", "cover": "138312.jpg", "gallery": ["138311.jpg", "138312.jpg", "138313.jpg"]},
        ],
    ),
    one_size_album(
        album_id="243238766",
        brand="Bape",
        category="Acessórios",
        type="Boné",
        source_model="126250343",
        source_price={"hat": "￥72"},
        colorways=[
            {"color": "Black / White", "slug": "black-white", "cover": "118377.jpg", "gallery": ["118377.jpg", "118379.jpg", "118380.jpg", "118381.jpg", "118382.jpg", "118394.jpg", "118395.jpg", "118396.jpg"]},
            {"color": "Green / White", "slug": "green-white", "cover": "118383.jpg", "gallery": ["118383.jpg", "118384.jpg", "118385.jpg", "118387.jpg"]},
            {"color": "Red / White", "slug": "red-white", "cover": "118386.jpg", "gallery": ["118386.jpg", "118388.jpg", "118389.jpg", "118390.jpg"]},
            {"color": "Blue / White", "slug": "blue-white", "cover": "118391.jpg", "gallery": ["118391.jpg", "118392.jpg", "118393.jpg", "118397.jpg"]},
        ],
    ),
    one_size_album(
        album_id="228508306",
        brand="Stussy",
        category="Acessórios",
        type="Boné",
        source_model="123180643",
        source_price={"hat": "￥68"},
        colorways=[
            {"color": "White", "slug": "white", "cover": "040421.jpg", "gallery": ["040421.jpg", "040422.jpg", "040423.jpg"]},
            {"color": "Tan", "slug": "tan", "cover": "040424.jpg", "gallery": ["040424.jpg", "040425.jpg", "040426.jpg"]},
            {"color": "Black", "slug": "black", "cover": "040427.jpg", "gallery": ["040427.jpg", "040428.jpg", "040429.jpg", "040430.jpg", "040431.jpg", "040432.jpg", "040433.jpg", "040434.jpg", "040435.jpg", "040436.jpg", "040437.jpg", "040438.jpg"]},
        ],
    ),
    {
        "album_id": "222712241",
        "brand": "Fear of God Essentials",
        "category": "Moletons",
        "type": "Hoodie",
        "source_model": "3201101117",
        "source_price": {"hoodie": "￥175"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["053543.png"],
        "colorways": [
            {"color": "White New York", "slug": "white-new-york", "cover": "053548.jpg", "gallery": ["053548.jpg", "053549.jpg", "053550.jpg", "053551.jpg", "053552.jpg", "053553.jpg"]},
            {"color": "Cream New York", "slug": "cream-new-york", "cover": "053554.jpg", "gallery": ["053554.jpg", "053555.jpg", "053556.jpg"]},
            {"color": "Black Chicago", "slug": "black-chicago", "cover": "053557.jpg", "gallery": ["053557.jpg", "053558.jpg", "053559.jpg"]},
            {"color": "Grey Essentials", "slug": "grey-essentials", "cover": "053560.jpg", "gallery": ["053560.jpg", "053561.jpg", "053562.jpg", "053563.jpg", "053564.jpg", "053565.jpg"]},
            {"color": "Cream Essentials", "slug": "cream-essentials", "cover": "053566.jpg", "gallery": ["053566.jpg", "053567.jpg", "053568.jpg", "053572.jpg", "053573.jpg", "053574.jpg", "053575.jpg", "053576.jpg", "053577.jpg"]},
            {"color": "Black Essentials", "slug": "black-essentials", "cover": "053569.jpg", "gallery": ["053569.jpg", "053570.jpg", "053571.jpg"]},
        ],
    },
    {
        "album_id": "242826585",
        "brand": "Supreme",
        "category": "Camisetas",
        "type": "T-Shirt",
        "source_model": "4206220502",
        "source_price": {"shirt": "￥98"},
        "sizes": ["S", "M", "L", "XL"],
        "size_charts": ["039661.png"],
        "colorways": [
            {"color": "Black", "slug": "black", "cover": "050244.jpg", "gallery": ["050244.jpg", "050245.jpg", "050246.jpg", "050247.jpg", "050249.jpg", "050250.jpg", "050251.jpg", "050252.jpg", "050253.jpg"]},
            {"color": "Brown", "slug": "brown", "cover": "050254.jpg", "gallery": ["050254.jpg", "050255.jpg", "050256.jpg", "050257.jpg", "050258.jpg", "050259.jpg"]},
            {"color": "White", "slug": "white", "cover": "050260.jpg", "gallery": ["050260.jpg", "050261.jpg", "050262.jpg", "050263.jpg", "050264.jpg", "050265.jpg"]},
            {"color": "Red", "slug": "red", "cover": "050266.jpg", "gallery": ["050266.jpg", "050267.jpg", "050268.jpg", "050269.jpg", "050270.jpg", "050271.jpg", "050272.jpg"]},
            {"color": "Purple", "slug": "purple", "cover": "050273.jpg", "gallery": ["050273.jpg", "050274.jpg", "050275.jpg", "050276.jpg", "050277.jpg", "050279.jpg"]},
        ],
    },
    {
        "album_id": "246998800",
        "brand": "Nike",
        "category": "Jaquetas",
        "type": "Jaqueta",
        "source_model": "2207251677",
        "source_price": {"jacket": "￥178"},
        "sizes": ["S", "M", "L", "XL", "2XL"],
        "size_charts": ["061926.png"],
        "colorways": [
            {"color": "White / Red", "slug": "white-red", "cover": "061931.jpg", "gallery": ["061931.jpg", "061932.jpg", "061933.jpg", "061945.jpg", "061946.jpg", "061941.jpg"]},
            {"color": "Grey / Black", "slug": "grey-black", "cover": "061934.jpg", "gallery": ["061934.jpg", "061935.jpg", "061947.jpg", "061948.jpg", "061942.jpg"]},
            {"color": "Navy / White", "slug": "navy-white", "cover": "061936.jpg", "gallery": ["061936.jpg", "061937.jpg", "061939.jpg", "061949.jpg", "061950.jpg"]},
            {"color": "Black / White", "slug": "black-white", "cover": "061940.jpg", "gallery": ["061940.jpg", "061952.jpg", "061955.jpg"]},
        ],
    },
]


BATCH_ALBUMS = {"01": BATCH_01_ALBUMS, "02": BATCH_02_ALBUMS, "03": BATCH_03_ALBUMS}


@dataclass
class AlbumContext:
    root: Path
    album: dict
    manifest_by_name: dict[str, dict]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_album_contexts(source_root: Path) -> dict[str, AlbumContext]:
    contexts = {}
    for albums_path in source_root.glob("*/albums.json"):
        manifest_path = albums_path.parent / "manifest.json"
        if not manifest_path.exists() or albums_path.stat().st_size <= 10 or manifest_path.stat().st_size <= 10:
            continue
        albums = json.loads(albums_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifests_by_album: dict[str, dict[str, dict]] = {}
        for item in manifest:
            album_id = str(item.get("album_id") or "")
            name = Path(str(item.get("file") or "")).name
            if album_id and name:
                manifests_by_album.setdefault(album_id, {})[name] = item
        for album in albums:
            album_id = str(album.get("album_id") or "")
            if not album_id:
                continue
            current = contexts.get(album_id)
            if current and len(current.album.get("image_files") or []) >= len(album.get("image_files") or []):
                continue
            contexts[album_id] = AlbumContext(albums_path.parent, album, manifests_by_album.get(album_id, {}))
    return contexts


def normalize_key(value: str) -> str:
    return " ".join((value or "").casefold().split())


def unique_keep_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def product_name(album_plan: dict, color: str) -> str:
    return f"{album_plan['brand']} {album_plan['type']} {color}"


def product_slug(album_plan: dict, color_slug: str) -> str:
    from app.utils.slug import make_slug

    return make_slug(f"{album_plan['brand']} {album_plan['type']} {album_plan['source_model']} {color_slug}")


def selected_image_names(colorway: dict, size_charts: list[str]) -> list[str]:
    charts = unique_keep_order(list(size_charts))
    gallery_limit = max(0, 12 - len(charts))
    gallery = unique_keep_order(list(colorway["gallery"]))[:gallery_limit]
    return gallery + charts


def image_meta(context: AlbumContext, filename: str) -> dict:
    source_path = context.root / "images" / filename
    manifest = context.manifest_by_name.get(filename, {})
    return {
        "filename": filename,
        "source_path": str(source_path),
        "exists": source_path.exists(),
        "sha256": manifest.get("sha256") or (file_sha256(source_path) if source_path.exists() else None),
        "mime_type": manifest.get("mime") or manifest.get("mime_type"),
        "width": manifest.get("width"),
        "height": manifest.get("height"),
        "source_url": manifest.get("source_url"),
        "position": manifest.get("position"),
    }


def build_plan(*, source_root: Path, max_products: int, batch_id: str = "01", album_plans: list[dict] | None = None) -> dict:
    album_plans = album_plans if album_plans is not None else BATCH_ALBUMS[batch_id]
    contexts = load_album_contexts(source_root)
    plan = {
        "created_at": now_iso(),
        "mode": "dry-run",
        "batch_id": batch_id,
        "source_root": str(source_root),
        "limit": max_products,
        "rule": {"color": "PRODUTO", "size": "VARIANTE"},
        "albums_analyzed": len(album_plans),
        "albums_used": 0,
        "products": [],
        "skips": [],
        "reviews": [],
    }
    for album_plan in album_plans:
        album_id = album_plan["album_id"]
        if album_id == PILOT_ALBUM_ID:
            plan["skips"].append({"album_id": album_id, "reason": "SKIP_PILOT_ALREADY_IMPORTED"})
            continue
        context = contexts.get(album_id)
        if not context:
            plan["reviews"].append({"album_id": album_id, "reason": "REVIEW_ALBUM_NOT_FOUND"})
            continue
        album_products = []
        for colorway in album_plan["colorways"]:
            images = [image_meta(context, name) for name in selected_image_names(colorway, album_plan["size_charts"])]
            missing = [item["filename"] for item in images if not item["exists"]]
            useful_count = len([item for item in images if item["exists"] and item["filename"] not in album_plan["size_charts"]])
            import_status = "READY"
            reasons = []
            if len(album_plan["sizes"]) == 0:
                import_status = "REVIEW"
                reasons.append("SKIP_SIZES_UNKNOWN")
            if useful_count < 3:
                import_status = "REVIEW"
                reasons.append("REVIEW_NOT_ENOUGH_IMAGES")
            if missing:
                import_status = "REVIEW"
                reasons.append("REVIEW_MISSING_IMAGES")
            album_products.append(
                {
                    "source_album_id": album_id,
                    "source_album_url": context.album.get("album_url"),
                    "source_title": context.album.get("title"),
                    "source_model": album_plan["source_model"],
                    "name": product_name(album_plan, colorway["color"]),
                    "slug": product_slug(album_plan, colorway["slug"]),
                    "sku": f"DZ-{album_plan['brand'].upper().replace(' ', '-')}-{album_plan['source_model']}-{colorway['slug'].upper()}",
                    "brand": album_plan["brand"],
                    "category": album_plan["category"],
                    "product_type": album_plan["type"],
                    "colorway": colorway["color"],
                    "sizes": album_plan["sizes"],
                    "main_image": colorway["cover"],
                    "gallery": [item["filename"] for item in images],
                    "images": images,
                    "size_charts": album_plan["size_charts"],
                    "source_price": album_plan["source_price"],
                    "confidence": "ALTA",
                    "duplicate_status": "UNKNOWN",
                    "import_status": import_status,
                    "review_reasons": reasons,
                }
            )
        if len(plan["products"]) + len(album_products) > max_products:
            plan["skips"].append({"album_id": album_id, "reason": "SKIP_LIMIT_WOULD_BE_EXCEEDED", "products": len(album_products)})
            continue
        plan["albums_used"] += 1
        plan["products"].extend(album_products)
    return plan


def mask_database_url() -> str:
    from sqlalchemy.engine.url import make_url

    return str(make_url(settings.database_url).set(password="***"))


def products_json_state() -> dict:
    path = PROJECT_ROOT / "frontend" / "data" / "products.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"path": str(path), "count": len(payload.get("products", [])), "sha256": file_sha256(path)}


def db_counts(db) -> dict:
    return {
        "products": db.execute(select(func.count()).select_from(Product)).scalar_one(),
        "variants": db.execute(select(func.count()).select_from(ProductVariant)).scalar_one(),
        "images": db.execute(select(func.count()).select_from(ProductImage)).scalar_one(),
        "brands": db.execute(select(func.count()).select_from(Brand)).scalar_one(),
        "categories": db.execute(select(func.count()).select_from(Category)).scalar_one(),
    }


def logical_backup(path: Path, *, batch_id: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    output = path / f"dripzone-before-yupoo-batch-{batch_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    with SessionLocal() as db:
        data = {"created_at": now_iso(), "database_url": mask_database_url(), "counts": db_counts(db), "tables": {}}
        from sqlalchemy import text

        for table in ("products", "product_variants", "product_images", "brands", "categories"):
            rows = db.execute(text(f"select * from {table} order by id")).all()
            data["tables"][table] = [dict(row._mapping) for row in rows]
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return output


def find_or_create_resource(db, model, *, name: str, slug: str):
    existing = db.execute(select(model).where(func.lower(model.slug) == slug.casefold())).scalar_one_or_none()
    if existing:
        return existing, False
    resource = model(name=name, slug=slug, is_active=True, position=0)
    db.add(resource)
    db.flush()
    return resource, True


def validate_duplicate_status(db, item: dict) -> str:
    slug_match = db.execute(select(Product).where(Product.slug == item["slug"])).scalar_one_or_none()
    if slug_match:
        return "JA_EXISTENTE"
    normalized = normalize_key(item["name"])
    for product in db.execute(select(Product).where(Product.brand.has(Brand.name == item["brand"]))).scalars():
        if normalize_key(product.name) == normalized:
            return "JA_EXISTENTE"
    return "NOVO"


def deterministic_filename(meta: dict, source_path: Path) -> str:
    sha = meta.get("sha256") or file_sha256(source_path)
    return f"{int(meta.get('position') or 0):03d}-{sha[:16]}{source_path.suffix.lower() or '.jpg'}"


def copy_image_for_product(db, product: Product, item: dict, meta: dict, *, position: int, created_paths: list[Path]) -> dict:
    ensure_canonical_upload_write_allowed()
    source_path = Path(meta["source_path"])
    if not source_path.exists():
        raise FileNotFoundError(str(source_path))
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(source_path)
        image = ImageOps.exif_transpose(image)
        image.load()
    upload_root = Path(settings.upload_directory)
    folder = ensure_child_path(upload_root, upload_root / "products" / product.public_id)
    folder.mkdir(parents=True, exist_ok=True)
    filename = deterministic_filename(meta, source_path)
    target = ensure_child_path(folder, folder / filename)
    shutil.copy2(source_path, target)
    created_paths.append(target)
    public_url = f"/uploads/products/{product.public_id}/{filename}"
    record = ProductImage(
        product_id=product.id,
        filename=filename,
        storage_path=str(target),
        public_url=public_url,
        mime_type=meta.get("mime_type") or "application/octet-stream",
        size_bytes=int(target.stat().st_size),
        width=int(meta.get("width") or image.width),
        height=int(meta.get("height") or image.height),
        alt_text=f"{item['name']} - {'capa' if meta['filename'] == item['main_image'] else 'galeria'}",
        is_primary=meta["filename"] == item["main_image"],
        position=position,
    )
    db.add(record)
    return {"original": meta["filename"], "public_url": public_url, "storage_path": str(target)}


def import_product(db, item: dict) -> dict:
    duplicate_status = validate_duplicate_status(db, item)
    if duplicate_status == "JA_EXISTENTE":
        return {"status": "SKIPPED_ALREADY_EXISTS", "slug": item["slug"], "name": item["name"]}
    if item["import_status"] != "READY":
        return {"status": "REVIEW", "slug": item["slug"], "name": item["name"], "reasons": item["review_reasons"]}
    from app.utils.slug import make_slug

    brand, brand_created = find_or_create_resource(db, Brand, name=item["brand"], slug=make_slug(item["brand"]))
    category, category_created = find_or_create_resource(db, Category, name=item["category"], slug=make_slug(item["category"]))
    variants = [
        VariantCreate(
            sku=f"{item['sku']}-{size}",
            size=size,
            color=None,
            stock_quantity=0,
            price_override=None,
            is_active=True,
            position=index,
        )
        for index, size in enumerate(item["sizes"], start=1)
    ]
    payload = ProductCreate(
        name=item["name"],
        slug=item["slug"],
        sku=item["sku"],
        short_description=f"{item['brand']} {item['product_type']} na colorway {item['colorway']}.",
        description=f"{item['brand']} {item['product_type']} na colorway {item['colorway']}. Produto em draft com preço e estoque pendentes. Consulte a tabela de medidas na galeria.",
        brand_id=brand.id,
        category_id=category.id,
        product_type=item["product_type"],
        price=Decimal("0.00"),
        cost_price=None,
        track_inventory=True,
        stock_quantity=0,
        minimum_stock=0,
        allow_backorder=False,
        availability="unavailable",
        ready_to_ship=False,
        status="draft",
        visibility="hidden",
        is_featured=False,
        is_new=False,
        is_best_seller=False,
        main_image_alt=item["name"],
        variants=variants,
    )
    created_paths: list[Path] = []
    try:
        product = create_product(db, payload, user_id=None)
        db.flush()
        copied = []
        for position, meta in enumerate(item["images"]):
            copied.append(copy_image_for_product(db, product, item, meta, position=position, created_paths=created_paths))
        db.flush()
        primary_count = len([image for image in product.images if image.is_primary])
        if primary_count != 1:
            raise RuntimeError(f"Produto sem uma unica imagem primaria: {item['slug']}")
        db.commit()
        return {
            "status": "CREATED",
            "id": product.id,
            "public_id": product.public_id,
            "slug": product.slug,
            "name": product.name,
            "brand_created": brand_created,
            "category_created": category_created,
            "variants": len(product.variants),
            "images": len(copied),
            "copied": copied,
        }
    except Exception:
        db.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise


def apply_duplicate_checks(plan: dict) -> None:
    with SessionLocal() as db:
        for item in plan["products"]:
            item["duplicate_status"] = validate_duplicate_status(db, item)
            if item["duplicate_status"] != "NOVO":
                item["import_status"] = "SKIP"


def run_import(plan: dict) -> dict:
    os.environ.setdefault("DRIPZONE_ALLOW_HOST_UPLOAD_WRITES", "1")
    apply_duplicate_checks(plan)
    result = {
        "started_at": now_iso(),
        "database_url": mask_database_url(),
        "database_dialect": engine.dialect.name,
        "products_json_before": products_json_state(),
        "before": {},
        "after": {},
        "items": [],
        "summary": {},
    }
    with SessionLocal() as db:
        result["before"] = db_counts(db)
    for item in plan["products"]:
        with SessionLocal() as db:
            try:
                result["items"].append(import_product(db, item))
            except Exception as exc:
                result["items"].append({"status": "ERROR", "slug": item["slug"], "name": item["name"], "error": str(exc)})
    with SessionLocal() as db:
        result["after"] = db_counts(db)
        created_slugs = [item["slug"] for item in result["items"] if item.get("status") == "CREATED"]
        products = db.execute(select(Product).where(Product.slug.in_(created_slugs))).scalars().all() if created_slugs else []
        result["validation"] = {
            "products_found": len(products),
            "draft_count": sum(product.status == "draft" for product in products),
            "published_count": sum(product.status == "published" for product in products),
            "hidden_count": sum(product.visibility == "hidden" for product in products),
            "variant_count": sum(len(product.variants) for product in products),
            "image_count": sum(len(product.images) for product in products),
            "missing_files": sum(1 for product in products for image in product.images if not Path(image.storage_path).exists()),
        }
    result["products_json_after"] = products_json_state()
    result["summary"] = {
        "created": sum(1 for item in result["items"] if item["status"] == "CREATED"),
        "skipped_existing": sum(1 for item in result["items"] if item["status"] == "SKIPPED_ALREADY_EXISTS"),
        "review": sum(1 for item in result["items"] if item["status"] == "REVIEW"),
        "errors": sum(1 for item in result["items"] if item["status"] == "ERROR"),
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importador Yupoo em lote controlado para drafts DripZone.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Gera plano sem alterar banco/uploads.")
    mode.add_argument("--import", dest="do_import", action="store_true", help="Executa importacao real dos itens READY.")
    parser.add_argument("--batch", choices=sorted(BATCH_ALBUMS), default="01")
    parser.add_argument("--source-root", default=str(PROJECT_ROOT / "downloads" / "yupoo"))
    parser.add_argument("--max-products", type=int, default=50)
    parser.add_argument("--plan-output")
    parser.add_argument("--result-output")
    parser.add_argument("--backup-dir", default=str(ROOT / "storage" / "database" / "backups"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root)
    plan_output = Path(args.plan_output) if args.plan_output else Path(gettempdir()) / f"dripzone-batch-{args.batch}-plan.json"
    result_output = Path(args.result_output) if args.result_output else Path(gettempdir()) / f"dripzone-batch-{args.batch}-result.json"
    plan = build_plan(source_root=source_root, max_products=args.max_products, batch_id=args.batch)
    apply_duplicate_checks(plan)
    plan_output.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[DRY-RUN] plano salvo em {plan_output}")
    print(f"[DRY-RUN] produtos potenciais: {len(plan['products'])}")
    print(f"[DRY-RUN] ready: {sum(1 for item in plan['products'] if item['import_status'] == 'READY')}")
    if args.dry_run:
        return 0
    backup = logical_backup(Path(args.backup_dir), batch_id=args.batch)
    result = run_import(plan)
    result["backup"] = str(backup)
    result_output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[IMPORT] resultado salvo em {result_output}")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 1 if result["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
