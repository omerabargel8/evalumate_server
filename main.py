import array
import collections
import json
import statistics
from io import BytesIO

import requests
from flask import Flask, request, make_response

from lxml import etree

from currency_converter import CurrencyConverter

app = Flask(__name__)


from googletrans import Translator
translator = Translator()



@app.route('/', methods=['GET'])
def index():
    return "Works"

PRICE_SIGNS_TO_CODES = {
    "€": "EUR",
    "$": "USD",
    "₽": "RUB"
}

MANUAL_CARE_BLACKLIST = {"projector", "refrigerator", "computer", "laptop", "macbook", "television", "tv"}

MANUAL_CARE_WHITELIST = {"ancient", "antique", "boutique"}

TAGS_FILTER_BLACKLIST = {"for", "epson", "samsung", "toshiba"}

def evaluate_product_by_url(yandex_url):
    html = requests.get(yandex_url).text
    root = etree.HTML(html)

    tags_elements = root.xpath("//div[@class='CbirItem CbirTags']//a[contains(@class,'Tags-Item')]")
    tags = [''.join(list(t.itertext())) for t in tags_elements]
    tags = [translator.translate(t, src="ru").text.lower() for t in tags]
    #tags = [ts.google(t, "ru").lower() for t in tags]
    tags_words = ' '.join(tags).split(' ')

    word_counter = collections.Counter(tags_words)
    most_common = word_counter.most_common()
    for item in most_common:
        if item[0] not in TAGS_FILTER_BLACKLIST:
            common_tag = item[0]
            break

    print(f"Tags: {tags}. Most common tag: {common_tag}")

    c = CurrencyConverter()
    price_elements = root.xpath("//span[@class = 'Price']")

    prices = []
    for element in price_elements:
        text_parts = list(element.itertext())
        price = int(text_parts[0].replace(" ", "").replace(' ', ""))
        price_sign = text_parts[-1]
        if price_sign not in PRICE_SIGNS_TO_CODES:
            raise RuntimeError(f"Unknown price sign: {price_sign}")

        price_currency = PRICE_SIGNS_TO_CODES[price_sign]
        price = int(c.convert(price, price_currency, "ILS"))
        prices.append(price)

    prices = sorted(prices)
    prices = prices[1:-1]
    print(f"Prices: {sorted(prices)}")

    average_price = sum(prices) / len(prices)
    print(f"Average in NIS: {average_price}")
    stdev = statistics.stdev(prices)
    print(f"Stdev: {stdev}")

    # Determine if manual care needed
    if common_tag in MANUAL_CARE_WHITELIST:
        manual_care_needed = True
    elif common_tag in MANUAL_CARE_BLACKLIST:
        manual_care_needed = False
    elif stdev < 300:
        manual_care_needed = False
    else:
        manual_care_needed = True
        #manual_care_needed = any(set(tags_words).intersection(MANUAL_CARE_WHITELIST))

    return {
        "price": average_price,
        "stdev": stdev,
        "tags": tags,
        "common_tag": common_tag,
        "manual_care_needed": manual_care_needed
    }


@app.route("/recognize", methods=['POST'])
def recognize_product():
    #product_image = request.files['img']
    bytes = BytesIO(array.array('B', eval(request.data)).tostring())

    searchUrl = 'https://yandex.ru/images/search'
    files = {'upfile': ('blob', bytes, 'image/jpeg')}
    params = {'rpt': 'imageview', 'format': 'json',
              'request': '{"blocks":[{"block":"b-page_type_search-by-image__link"},{"block":"extra-content","params":{},"version":2}]}'}
    response = requests.post(searchUrl, params=params, files=files)
    query_string = json.loads(response.content)['blocks'][0]['params']['url']
    img_search_url = searchUrl + '?' + query_string
    try:
        result = evaluate_product_by_url(img_search_url)
        return make_response(
            json.dumps({
                "result": result,
                "yandex_url": img_search_url
            }), 200)
    except Exception as e:
        error = str(e)
        return make_response(
            json.dumps({
                "error": error
            }), 200)


app.run(host="0.0.0.0")