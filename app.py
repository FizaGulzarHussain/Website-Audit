from __future__ import annotations
import io
import re
import time
import json
import socket
import random
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from pypdf import PdfWriter

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Website Audit",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# MINIMAL CSS POLISH
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.tech-badge {
    display:inline-block; padding:2px 9px; border-radius:20px;
    font-size:11px; font-weight:600; margin:2px 2px;
}
.badge-wordpress  { background:#21759B22; color:#21759B; }
.badge-shopify    { background:#96BF4822; color:#5E8E3E; }
.badge-wix        { background:#FAAD1422; color:#B07D00; }
.badge-squarespace{ background:#00000022; color:#333; }
.badge-joomla     { background:#F44E2722; color:#C03D1E; }
.badge-drupal     { background:#0678BE22; color:#0678BE; }
.badge-webflow    { background:#4353FF22; color:#2D3AC0; }
.badge-magento    { background:#EE672222; color:#C24E12; }
.badge-unknown    { background:#88888822; color:#555; }
.badge-plugin     { background:#6C63FF22; color:#4B44CC; }
.score-chip {
    display:inline-block; padding:4px 12px; border-radius:20px;
    font-size:13px; font-weight:700; margin:0 4px;
}
/* Download button — matches the primary blue #1F62FF */
[data-testid="stDownloadButton"] > button {
    background-color: #1F62FF !important;
    color: #FFFFFF !important;
    border: none !important;
    font-weight: 600 !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background-color: #1750D6 !important;
    color: #FFFFFF !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
SERPER_API_KEY = "ed92cd653e12f00849abbdedd5dd835efa952391"
SERPER_URL     = "https://google.serper.dev/search"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/123.0.0.0",
]

AGGREGATOR_DOMAINS = [
    "yelp.com", "yellowpages.com", "tripadvisor.com", "google.com",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com",
    "wikipedia.org", "reddit.com", "amazon.com", "trustpilot.com",
    "glassdoor.com", "indeed.com", "zomato.com", "justdial.com",
    "foursquare.com", "bing.com", "yahoo.com", "maps.google.com",
]

# ─────────────────────────────────────────────────────────────────────────────
# SEARCH FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
def _headers():
    return {"User-Agent": random.choice(USER_AGENTS)}

def _is_aggregator(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        return any(agg in domain for agg in AGGREGATOR_DOMAINS)
    except Exception:
        return False

def search_serper(query: str, num: int = 30) -> list[dict]:
    payload = {"q": query, "num": min(num, 100)}
    hdrs    = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    resp    = requests.post(SERPER_URL, json=payload, headers=hdrs, timeout=15)
    resp.raise_for_status()
    data    = resp.json()
    results = []
    for item in data.get("organic", [])[:num]:
        results.append({
            "business_name": item.get("title", "").strip(),
            "source_url":    item.get("link", "").strip(),
            "snippet":       item.get("snippet", "").strip(),
            "source":        "Google (Serper)",
        })
    kg = data.get("knowledgeGraph", {})
    if kg and kg.get("website"):
        results.insert(0, {
            "business_name": kg.get("title", "").strip(),
            "source_url":    kg.get("website", "").strip(),
            "snippet":       kg.get("description", "").strip(),
            "source":        "Google KG",
        })
    return results

def search_duckduckgo(query: str, num: int = 20) -> list[dict]:
    url    = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
    time.sleep(random.uniform(1.5, 3))
    resp   = requests.get(url, params=params, headers=_headers(), timeout=15)
    resp.raise_for_status()
    data   = resp.json()
    results = []
    for topic in data.get("RelatedTopics", [])[:num]:
        if isinstance(topic, dict) and "Text" in topic:
            text = topic.get("Text", "")
            name = text.split(" - ")[0] if " - " in text else text[:60]
            results.append({
                "business_name": name.strip(),
                "source_url":    topic.get("FirstURL", ""),
                "snippet":       text.strip(),
                "source":        "DuckDuckGo",
            })
    return results

def search_bing(query: str, num: int = 20) -> list[dict]:
    url    = "https://www.bing.com/search"
    params = {"q": query, "count": num}
    time.sleep(random.uniform(1.5, 3))
    resp   = requests.get(url, params=params, headers=_headers(), timeout=15)
    resp.raise_for_status()
    soup   = BeautifulSoup(resp.text, "lxml")
    results = []
    for li in soup.find_all("li", class_=re.compile("b_algo")):
        a = li.find("a", href=True)
        p = li.find("p")
        if a and a.get("href", "").startswith("http"):
            results.append({
                "business_name": a.get_text(strip=True),
                "source_url":    a["href"],
                "snippet":       p.get_text(strip=True) if p else "",
                "source":        "Bing",
            })
    return results[:num]

def multi_engine_search(industry: str, area: str, max_results: int = 20) -> tuple[list[dict], list[str]]:
    """Search across multiple engines, deduplicate, filter aggregators."""
    query   = f"{industry} in {area}"
    all_raw = []
    engines_used = []

    # 1. Serper/Google
    try:
        r = search_serper(query, num=max_results * 3)
        all_raw.extend(r)
        engines_used.append("Google (Serper)")
    except Exception as e:
        engines_used.append(f"Google failed: {e}")

    # 2. Bing
    try:
        r = search_bing(query, num=max_results * 2)
        all_raw.extend(r)
        engines_used.append("Bing")
    except Exception as e:
        engines_used.append(f"Bing failed: {e}")

    # 3. DuckDuckGo
    try:
        r = search_duckduckgo(query, num=max_results * 2)
        all_raw.extend(r)
        engines_used.append("DuckDuckGo")
    except Exception as e:
        engines_used.append(f"DuckDuckGo failed: {e}")

    # Deduplicate by domain
    seen   = set()
    unique = []
    for item in all_raw:
        url = item.get("source_url", "")
        if not url or _is_aggregator(url):
            continue
        try:
            domain = urlparse(url).netloc.lower()
        except Exception:
            domain = url
        if domain and domain not in seen:
            seen.add(domain)
            unique.append(item)

    return unique[:max_results], engines_used

# ─────────────────────────────────────────────────────────────────────────────
# TECH DETECTION  — expanded signatures + multi-signal scoring
# ─────────────────────────────────────────────────────────────────────────────

CMS_SIGNATURES: dict[str, list[tuple[str, float]]] = {
    "WordPress": [
        (r"/wp-content/themes/",            2.0),
        (r"/wp-content/plugins/",           2.0),
        (r"/wp-includes/js/",               2.0),
        (r"/wp-json/",                      1.5),
        (r"wp-embed\.min\.js",              1.5),
        (r'content="WordPress',             1.5),
        (r"xmlrpc\.php",                    1.0),
        (r"/wp-content/uploads/",           1.0),
        (r"wp-block-",                      0.8),
        (r"class=\"wp-",                    0.7),
        (r"WordPress",                      0.5),
    ],
    "Shopify": [
        (r"cdn\.shopify\.com",              2.0),
        (r"myshopify\.com",                 2.0),
        (r"Shopify\.theme",                 2.0),
        (r"shopify-section",                1.5),
        (r"shopify\.com/s/files/",          1.5),
        (r'"shopify"',                      1.0),
        (r"Shopify\.shop",                  1.0),
        (r"/collections/",                  0.5),
    ],
    "Wix": [
        (r"wixstatic\.com",                 2.0),
        (r"wix\.com/_api/",                 2.0),
        (r"X-Wix-Published-Version",        2.0),
        (r"wix-code",                       1.5),
        (r"\"wix\"",                        1.0),
        (r"parastorage\.com",               1.0),
        (r"wixsite\.com",                   1.5),
    ],
    "Squarespace": [
        (r"squarespace\.com",               2.0),
        (r"sqsp\.net",                      2.0),
        (r"static1\.squarespace\.com",      2.0),
        (r'"squarespace"',                  1.5),
        (r"Squarespace-Headers",            1.5),
        (r"sqs-layout",                     1.0),
        (r"data-sqs-type",                  1.0),
    ],
    "Webflow": [
        (r"webflow\.com",                   2.0),
        (r"webflow\.io",                    2.0),
        (r"data-wf-page",                   2.0),
        (r"data-wf-site",                   2.0),
        (r"webflow\.js",                    1.5),
        (r'"webflow"',                      1.0),
    ],
    "Joomla": [
        (r"/components/com_content",        2.0),
        (r"/components/com_",               1.5),
        (r'content="Joomla',                2.0),
        (r"joomla",                         1.0),
        (r"/media/system/js/",              0.8),
        (r"Joomla!",                        0.8),
        (r"/administrator/",                0.5),
    ],
    "Drupal": [
        (r"/sites/default/files/",          2.0),
        (r"Drupal\.settings",               2.0),
        (r'content="Drupal',                2.0),
        (r"drupal\.js",                     1.5),
        (r"drupal",                         0.8),
        (r"/misc/drupal\.js",               1.5),
        (r"X-Generator.*Drupal",            2.0),
    ],
    "Magento": [
        (r"Mage\.Cookies",                  2.0),
        (r"/skin/frontend/",                2.0),
        (r"magento",                        1.0),
        (r"var BLANK_URL",                  1.0),
        (r"Magento_",                       1.5),
        (r"/pub/static/frontend/",          1.5),
    ],
    "Ghost": [
        (r"content\.ghost\.io",             2.0),
        (r"ghost\.io",                      1.5),
        (r'content="Ghost',                 2.0),
        (r"ghost-theme",                    1.5),
        (r"/ghost/api/",                    2.0),
    ],
    "PrestaShop": [
        (r"prestashop",                     1.5),
        (r"/modules/blockcart/",            2.0),
        (r"presta",                         0.8),
        (r"/themes/default-bootstrap/",     2.0),
    ],
    "OpenCart": [
        (r"catalog/view/theme/",            2.0),
        (r"opencart",                       1.5),
        (r"route=common/home",              1.0),
    ],
    "HubSpot CMS": [
        (r"hs-scripts\.com",                2.0),
        (r"hubspot\.com",                   1.5),
        (r"hs-analytics",                   1.5),
        (r"hsforms\.net",                   1.5),
        (r"hbspt\.",                        1.0),
    ],
    "Next.js": [
        (r"_next/static/chunks/",           2.0),
        (r"__NEXT_DATA__",                  2.0),
        (r"_next/image",                    1.5),
        (r"next/dist/",                     1.0),
    ],
    "Nuxt.js": [
        (r"__nuxt",                         2.0),
        (r"_nuxt/",                         2.0),
        (r"nuxt-link",                      1.5),
        (r"window\.__nuxt",                 2.0),
    ],
    "Gatsby": [
        (r"gatsby-",                        1.5),
        (r"/static/gatsby-",                2.0),
        (r"window\.___gatsby",              2.0),
        (r"gatsby-image",                   1.5),
    ],
    "Craft CMS": [
        (r"craftcms",                       2.0),
        (r'content="Craft CMS',             2.0),
        (r"/cpresources/",                  1.5),
    ],
    "TYPO3": [
        (r"typo3",                          1.5),
        (r"/typo3conf/",                    2.0),
        (r'content="TYPO3',                 2.0),
    ],
    "Blogger": [
        (r"blogger\.com",                   2.0),
        (r"blogspot\.com",                  2.0),
        (r'content="blogger"',              2.0),
    ],
    "Medium": [
        (r"medium\.com",                    2.0),
        (r"medium-feed",                    1.5),
        (r"mediumcdn\.com",                 2.0),
    ],
    "Framer": [
        (r"framer\.com",                    2.0),
        (r"framerusercontent\.com",         2.0),
        (r"framer-motion",                  1.5),
    ],
    "Cargo": [
        (r"cargocollective\.com",           2.0),
        (r"cargo\.site",                    2.0),
    ],
    "BigCommerce": [
        (r"bigcommerce\.com",               2.0),
        (r"cdn\.bigcommerce\.com",          2.0),
        (r"bigcommerce",                    1.0),
    ],
    "WooCommerce (WP)": [
        (r"woocommerce",                    1.0),
        (r"/wc-api/",                       1.5),
        (r"wc_add_to_cart",                 1.5),
    ],
}

HEADER_CMS_MAP: dict[str, str] = {
    "x-shopify-stage":         "Shopify",
    "x-shopid":                "Shopify",
    "x-wix-request-id":        "Wix",
    "x-ghost-cache-status":    "Ghost",
    "x-drupal-cache":          "Drupal",
    "x-generator":             None,
    "x-powered-by-squarespace":"Squarespace",
    "x-mod-pagespeed":         None,
}

GENERATOR_MAP: dict[str, str] = {
    "wordpress":    "WordPress",
    "joomla":       "Joomla",
    "drupal":       "Drupal",
    "ghost":        "Ghost",
    "craft cms":    "Craft CMS",
    "typo3":        "TYPO3",
    "squarespace":  "Squarespace",
    "webflow":      "Webflow",
    "framer":       "Framer",
    "wix":          "Wix",
    "blogger":      "Blogger",
    "hubspot":      "HubSpot CMS",
    "bigcommerce":  "BigCommerce",
    "prestashop":   "PrestaShop",
    "opencart":     "OpenCart",
    "magento":      "Magento",
}

# CDNs / proxies that mask the real server — these are infrastructure,
# NOT the site's CMS or framework. Show them separately, not as the CMS label.
_INFRASTRUCTURE_LABELS: dict[str, str] = {
    "cloudflare": "Cloudflare CDN",
    "fastly":     "Fastly CDN",
    "akamai":     "Akamai CDN",
    "cloudfront": "AWS CloudFront",
    "bunnycdn":   "BunnyCDN",
    "b-cdn":      "BunnyCDN",
}

PLUGIN_SIGNATURES: dict[str, str] = {
    "WooCommerce":         r"woocommerce",
    "Elementor":           r"elementor",
    "Yoast SEO":           r"yoast|yoast-schema",
    "Rank Math SEO":       r"rank-math|rankmath",
    "Contact Form 7":      r"wpcf7|contact-form-7",
    "Gravity Forms":       r"gform_|gravityforms",
    "WPML":                r"\bwpml\b",
    "Akismet":             r"akismet",
    "Jetpack":             r"jetpack",
    "WP Rocket":           r"wp-rocket|wprocket",
    "All-in-One SEO":      r"aioseo|all-in-one-seo",
    "Divi Builder":        r"divi|et_pb_",
    "WPBakery":            r"wpb_|vc_",
    "Beaver Builder":      r"fl-builder|beaver-builder",
    "Google Analytics 4":  r"G-[A-Z0-9]{6,}|gtag\(.*G-",
    "Google Analytics UA": r"UA-\d{5,}-\d+",
    "Google Tag Manager":  r"googletagmanager\.com|GTM-[A-Z0-9]+",
    "Facebook Pixel":      r"fbq\(|facebook\.net/en_US/fbevents",
    "Hotjar":              r"hotjar\.com|hjid",
    "Clarity (Microsoft)": r"clarity\.ms|microsoft.*clarity",
    "Mixpanel":            r"mixpanel\.com",
    "Segment":             r"segment\.com|analytics\.js",
    "Intercom":            r"intercom\.io|intercomcdn",
    "Tawk.to":             r"tawk\.to",
    "Zendesk Chat":        r"zendesk\.com|zopim\.com",
    "Crisp Chat":          r"crisp\.chat",
    "Drift":               r"drift\.com",
    "Tidio":               r"tidio",
    "LiveChat":            r"livechatinc\.com",
    "Cloudflare":          r"cloudflare",
    "Fastly":              r"fastly",
    "AWS CloudFront":      r"cloudfront\.net",
    "Akamai":              r"akamai",
    "BunnyCDN":            r"b-cdn\.net",
    "reCAPTCHA":           r"recaptcha",
    "hCaptcha":            r"hcaptcha",
    "Bootstrap":           r"bootstrap\.min\.css|bootstrap\.css|bootstrap\.min\.js",
    "Tailwind CSS":        r"tailwind|tailwindcss",
    "jQuery":              r"jquery\.min\.js|jquery-\d",
    "React":               r"react\.production\.min|react-dom|__react",
    "Vue.js":              r"vue\.global|vue\.esm|vue@\d|createApp\(",
    "Angular":             r"angular\.min\.js|ng-version|zone\.js",
    "Alpine.js":           r"alpine\.min\.js|x-data=",
    "Next.js":             r"__NEXT_DATA__|_next/static",
    "Nuxt.js":             r"__nuxt|_nuxt/",
    "Svelte":              r"svelte-",
    "Stripe":              r"stripe\.com/v3|js\.stripe\.com",
    "PayPal":              r"paypal\.com/sdk",
    "WooPayments":         r"woopayments|woo-payment",
    "HubSpot Forms":       r"hsforms\.net|hbspt\.forms",
    "Mailchimp":           r"mailchimp\.com|mc\.js",
    "Klaviyo":             r"klaviyo\.com|kl-private",
    "ActiveCampaign":      r"activecampaign\.com",
    "ConvertKit":          r"convertkit\.com",
    "Cookiebot":           r"cookiebot\.com",
    "OneTrust":            r"onetrust\.com|onetrust-banner",
    "CookieYes":           r"cookieyes\.com",
}

def _extract_generator_meta(soup) -> str | None:
    tag = soup.find("meta", attrs={"name": re.compile(r"^generator$", re.I)})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None

def _resolve_unknown_cms(t: dict) -> tuple[str, str | None]:
    """
    When CMS detection returns 'Unknown', infer a human-readable label from
    plugins / frameworks / server header — without misleadingly naming a CDN
    (e.g. Cloudflare) as the site's technology.

    Returns (cms_label, confidence).
    """
    plugins_lc = " ".join(t.get("plugins", [])).lower()
    svr_raw    = t.get("server") or ""
    svr_lc     = svr_raw.lower()

    # ── Framework signals (reliable) ─────────────────────────────────────────
    if "next.js" in plugins_lc:
        return "Next.js", "medium"
    if "nuxt.js" in plugins_lc:
        return "Nuxt.js", "medium"
    if "react" in plugins_lc:
        return "Custom (React)", "low"
    if "angular" in plugins_lc:
        return "Custom (Angular)", "low"
    if "vue.js" in plugins_lc:
        return "Custom (Vue)", "low"

    # ── More plugin/framework signals before checking server header ─────────────
    if "wordpress" in plugins_lc or "woocommerce" in plugins_lc or "elementor" in plugins_lc:
        return "WordPress", "medium"
    if "shopify" in plugins_lc:
        return "Shopify", "medium"
    if "wix" in plugins_lc:
        return "Wix", "medium"
    if "squarespace" in plugins_lc:
        return "Squarespace", "medium"
    if "webflow" in plugins_lc:
        return "Webflow", "medium"
    if "drupal" in plugins_lc:
        return "Drupal", "medium"
    if "joomla" in plugins_lc:
        return "Joomla", "medium"
    if "svelte" in plugins_lc:
        return "Custom (Svelte)", "low"
    if "gatsby" in plugins_lc:
        return "Gatsby", "low"

    # ── Server header — skip if it only tells us about the CDN layer ──────────
    if svr_lc:
        for infra_key, infra_label in _INFRASTRUCTURE_LABELS.items():
            if infra_key in svr_lc:
                return "Unknown (via CDN)", "low"

        if "php" in svr_lc:
            return "Custom PHP site", "low"
        svr_label = svr_raw.split("/")[0].strip()[:20] or "Unknown server"
        return f"Custom site ({svr_label})", "low"

    return "Unknown", None


def detect_tech(url: str, timeout: int = 12) -> dict:
    result: dict = {
        "cms":            "Unknown",
        "cms_confidence": None,
        "plugins":        [],
        "frameworks":     [],
        "server":         None,
        "https":          url.startswith("https"),
        "ip":             None,
        "error":          None,
    }
    try:
        resp = requests.get(
            url, headers=_headers(), timeout=timeout,
            allow_redirects=True, stream=False,
        )
        raw_html = resp.text
        html_lc  = raw_html.lower()
        hdrs     = resp.headers
        hdrs_lc  = {k.lower(): v.lower() for k, v in hdrs.items()}

        soup = BeautifulSoup(raw_html, "lxml")

        result["server"] = (
            hdrs.get("Server") or hdrs.get("X-Powered-By") or
            hdrs.get("x-powered-by") or None
        )

        try:
            result["ip"] = socket.gethostbyname(urlparse(url).netloc)
        except Exception:
            pass

        cms_detected = "Unknown"
        confidence   = None

        # ── 1. <meta name="generator"> ────────────────────────────────────────
        gen = _extract_generator_meta(soup)
        if gen:
            gen_lc = gen.lower()
            for keyword, cms_name in GENERATOR_MAP.items():
                if keyword in gen_lc:
                    cms_detected = cms_name
                    confidence   = "high"
                    break

        # ── 2. Response headers ────────────────────────────────────────────────
        if cms_detected == "Unknown":
            for hdr_key, cms_name in HEADER_CMS_MAP.items():
                if hdr_key in hdrs_lc:
                    if cms_name:
                        cms_detected = cms_name
                        confidence   = "high"
                        break
                    elif hdr_key == "x-generator":
                        val = hdrs_lc[hdr_key]
                        for keyword, cname in GENERATOR_MAP.items():
                            if keyword in val:
                                cms_detected = cname
                                confidence   = "high"
                                break
                    if cms_detected != "Unknown":
                        break

            if cms_detected == "Unknown":
                xpb = hdrs_lc.get("x-powered-by", "")
                for keyword, cname in GENERATOR_MAP.items():
                    if keyword in xpb:
                        cms_detected = cname
                        confidence   = "high"
                        break

        # ── 3. Weighted HTML / header pattern scoring ──────────────────────────
        if cms_detected == "Unknown":
            best_cms   = "Unknown"
            best_score = 0.0
            combined   = html_lc + " " + str(hdrs_lc)

            for cms_name, patterns in CMS_SIGNATURES.items():
                total = 0.0
                for pat, weight in patterns:
                    if re.search(pat, combined, re.I):
                        total += weight
                if total > best_score:
                    best_score = total
                    best_cms   = cms_name

            if best_score >= 2.0:
                cms_detected = best_cms
                confidence   = "high" if best_score >= 3.0 else "medium"
            elif best_score >= 1.0:
                cms_detected = best_cms
                confidence   = "low"

        result["cms"]            = cms_detected
        result["cms_confidence"] = confidence

        # ── 4. Plugin / library detection ─────────────────────────────────────
        found = []
        for name, pat in PLUGIN_SIGNATURES.items():
            if re.search(pat, html_lc, re.I):
                found.append(name)
        result["plugins"] = found

    except Exception as e:
        result["error"] = str(e)

    return result

# ─────────────────────────────────────────────────────────────────────────────
# AUDIT
# ─────────────────────────────────────────────────────────────────────────────
try:
    from audit import audit_website
    from audit_pdf import generate_audit_pdf
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False
    def audit_website(url, progress_callback=None):
        try:
            start = time.time()
            r     = requests.get(url, headers=_headers(), timeout=15)
            ttfb  = round((time.time() - start) * 1000)
            soup  = BeautifulSoup(r.text, "lxml")
        except Exception:
            return {"url": url, "overall_score": 0, "breakdown": {}, "lighthouse_details": {}, "fastsite_projection": {}}

        score    = 0
        issues   = []
        strengths= []

        if url.startswith("https"):
            score += 15; strengths.append("HTTPS enabled")
        else:
            issues.append("No HTTPS")

        title = soup.find("title")
        if title and title.get_text(strip=True):
            score += 10; strengths.append("Title tag present")
        else:
            issues.append("Missing title tag")

        h1s = soup.find_all("h1")
        if len(h1s) == 1:
            score += 10; strengths.append("Single H1 tag")
        elif not h1s:
            issues.append("No H1 tag")

        meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        if meta and meta.get("content", "").strip():
            score += 10; strengths.append("Meta description present")
        else:
            issues.append("No meta description")

        ttfb_score = 30 if ttfb < 500 else (20 if ttfb < 1000 else 5)
        score += ttfb_score
        if ttfb < 500:
            strengths.append(f"Fast TTFB: {ttfb}ms")
        else:
            issues.append(f"Slow TTFB: {ttfb}ms")

        overall = min(score + 25, 100)
        return {
            "url": url,
            "overall_score": overall,
            "breakdown": {
                "seo": {"score": score, "issues": issues, "strengths": strengths, "details": {}},
            },
            "lighthouse_details": {},
            "fastsite_projection": {},
        }

    def generate_audit_pdf(audit, lang="en"):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet
            buf    = io.BytesIO()
            doc    = SimpleDocTemplate(buf, pagesize=A4)
            styles = getSampleStyleSheet()
            story  = [Paragraph(f"Audit: {audit.get('url')}", styles["Title"]),
                      Paragraph(f"Score: {audit.get('overall_score')}/100", styles["Normal"])]
            for cat, data in audit.get("breakdown", {}).items():
                story.append(Paragraph(f"{cat}: {data.get('score')}/100", styles["Heading2"]))
                for iss in data.get("issues", []):
                    story.append(Paragraph(f"⚠ {iss}", styles["Normal"]))
            doc.build(story)
            return buf.getvalue()
        except Exception:
            return b"%PDF-placeholder"

# ─────────────────────────────────────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────────────────────────────────────
_CMS_COLORS: dict[str, tuple[str, str]] = {
    "WordPress":        ("#21759B", "#21759B18"),
    "Shopify":          ("#5E8E3E", "#96BF4818"),
    "Wix":              ("#B07D00", "#FAAD1418"),
    "Squarespace":      ("#333333", "#33333318"),
    "Webflow":          ("#2D3AC0", "#4353FF18"),
    "Joomla":           ("#C03D1E", "#F44E2718"),
    "Drupal":           ("#0678BE", "#0678BE18"),
    "Magento":          ("#C24E12", "#EE672218"),
    "Ghost":            ("#738A94", "#738A9418"),
    "PrestaShop":       ("#DF0067", "#DF006718"),
    "Next.js":          ("#000000", "#00000015"),
    "Nuxt.js":          ("#00C58E", "#00C58E18"),
    "Gatsby":           ("#663399", "#66339918"),
    "HubSpot CMS":      ("#FF7A59", "#FF7A5918"),
    "Craft CMS":        ("#E5422B", "#E5422B18"),
    "TYPO3":            ("#FF8700", "#FF870018"),
    "Blogger":          ("#FF5722", "#FF572218"),
    "Framer":           ("#0099FF", "#0099FF18"),
    "BigCommerce":      ("#34313F", "#34313F18"),
    "WooCommerce (WP)": ("#7F54B3", "#7F54B318"),
    "OpenCart":         ("#23AEFF", "#23AEFF18"),
    "Medium":           ("#000000", "#00000015"),
    "Cargo":            ("#FF4D00", "#FF4D0018"),
    "Unknown":          ("#888888", "#88888815"),
}

def _cms_badge(cms: str, confidence: str | None = None) -> str:
    fg, bg = _CMS_COLORS.get(cms, ("#888888", "#88888815"))
    conf_icon = {"high": " ✓", "medium": " ~", "low": " "}.get(confidence or "", "")
    label = f"{cms}{conf_icon}"
    return (
        f'<span class="tech-badge" style="background:{bg};color:{fg};'
        f'border:1px solid {fg}55;font-weight:700;">{label}</span>'
    )

def _score_color(s):
    return "#2E7D32" if s >= 75 else ("#F57F17" if s >= 50 else "#C62828")

def render_score_chip(score: int) -> str:
    col = _score_color(score)
    return (
        f'<span class="score-chip" style="background:{col}22;color:{col};">'
        f'{score}/100</span>'
    )

def _render_tech_badges(t: dict) -> str:
    """Shared helper: build the HTML badge string for a tech-detection result dict."""
    cms  = t.get("cms", "Unknown")
    conf = t.get("cms_confidence")

    if cms == "Unknown":
        cms, conf = _resolve_unknown_cms(t)

    cms_html  = _cms_badge(cms, conf)
    plug_html = " ".join(
        f'<span class="tech-badge" style="background:#6C63FF18;color:#4B44CC;'
        f'border:1px solid #6C63FF44;">{p}</span>'
        for p in t.get("plugins", [])[:8]
    )
    svr_txt = t.get("server", "")
    svr = (
        f'<span class="tech-badge" style="background:#88888815;color:#555;'
        f'border:1px solid #88888844;">🖥 {svr_txt[:30]}</span>'
        if svr_txt else ""
    )
    err_txt = t.get("error", "")
    err = (
        f'<span class="tech-badge" style="background:#ff000015;color:#c00;'
        f'border:1px solid #ff000044;">⚠ {err_txt[:40]}</span>'
        if err_txt else ""
    )
    return cms_html + " " + plug_html + " " + svr + " " + err

# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────
st.title("Website Audit")

# ── STEP 1: Mode Selection ───────────────────────────────────────────────────
st.subheader("Step 1 — Choose Your Audit Mode")

mode = st.radio(
    "What would you like to do?",
    ["🔍 Search & Audit — Find businesses by industry & location",
     "🌐 Direct URL Audit — Audit a specific website URL"],
    horizontal=True,
    label_visibility="collapsed",
)
is_direct_mode = mode.startswith("🌐")

# Clear all results when the user switches between modes
prev_mode = st.session_state.get("_active_mode")
if prev_mode is not None and prev_mode != is_direct_mode:
    for key in ["audits", "results", "engines", "tech", "direct_tech",
                "direct_url_ready", "selected_for_audit", "_select_action"]:
        st.session_state.pop(key, None)
st.session_state["_active_mode"] = is_direct_mode

st.markdown("")  # spacer

# ── MODE A: Direct URL Audit ─────────────────────────────────────────────────
if is_direct_mode:
    st.markdown("**Enter the website URL you want to audit**")
    url_col, btn_col = st.columns([4, 1])
    with url_col:
        direct_url = st.text_input(
            "Website URL",
            placeholder="https://example.com",
            label_visibility="collapsed",
        )
    with btn_col:
        direct_go_btn = st.button("▶ Continue", type="primary", use_container_width=True)

    if direct_go_btn:
        raw = direct_url.strip()
        if not raw:
            st.warning("Please enter a website URL.")
        else:
            if not raw.startswith(("http://", "https://")):
                raw = "https://" + raw
            st.session_state["direct_url_ready"] = raw
            # Clear any stale state from previous runs
            st.session_state.pop("direct_tech", None)
            st.session_state.pop("audits", None)
            st.session_state.pop("results", None)
            st.rerun()

    # ── STEP 2 (Direct mode): Tech Stack Detection ───────────────────────────
    ready_url = st.session_state.get("direct_url_ready", "")
    if ready_url:
        st.markdown("")
        st.subheader("Step 2 — Detect Tech Stack")
        st.caption(f"URL: [{ready_url}]({ready_url})")

        direct_tech = st.session_state.get("direct_tech", {})
        already_detected = ready_url in direct_tech

        detect_col, skip_col = st.columns([2, 1])
        with detect_col:
            detect_btn = st.button(
                "🧪 Detect Tech Stack (CMS & Plugins)",
                use_container_width=True,
                disabled=already_detected,
            )
        with skip_col:
            skip_btn = st.button(
                "⏭ Skip — Go straight to audit",
                use_container_width=True,
            )

        if detect_btn:
            with st.spinner(f"Analysing {ready_url}…"):
                direct_tech[ready_url] = detect_tech(ready_url)
            st.session_state["direct_tech"] = direct_tech
            st.rerun()

        if already_detected:
            t = direct_tech[ready_url]
            st.markdown(
                "**Detected Tech Stack:** " + _render_tech_badges(t),
                unsafe_allow_html=True,
            )
            st.success("Tech detection complete! Proceed to the audit below.")

        # ── STEP 3 (Direct mode): Run Audit ──────────────────────────────────
        if already_detected or skip_btn:
            st.markdown("")
            st.subheader("Step 3 — Run Audit")
            already_has_audit = ready_url in st.session_state.get("audits", {})
            audit_btn_label = "🔄 Re-audit Site" if already_has_audit else "🚀 Audit Site"
            audit_btn = st.button(audit_btn_label, type="primary", use_container_width=True)
            if audit_btn:
                # Clear previous result so stale data doesn't persist during fetch
                st.session_state.setdefault("audits", {}).pop(ready_url, None)
                with st.spinner(f"Auditing {ready_url}…"):
                    result = audit_website(ready_url)
                st.session_state["audits"] = {ready_url: result}
                st.rerun()

# ── MODE B: Search Businesses ────────────────────────────────────────────────
else:
    st.markdown("**Search for businesses by industry & location**")
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        industry = st.text_input("Industry", placeholder="e.g. hospitals, gyms, cafes")
    with col2:
        area     = st.text_input("Location", placeholder="e.g. Pakistan, Germany, Mumbai")
    with col3:
        max_results = st.number_input("Max Results", 1, 50, 15)

    search_btn = st.button("🔍 Search Businesses", type="primary", use_container_width=True)

    if search_btn:
        if not industry or not area:
            st.warning("Please enter both Industry and Location.")
        else:
            status = st.empty()
            with st.spinner("Querying Google, Bing & DuckDuckGo…"):
                results, engines = multi_engine_search(industry, area, int(max_results))
            st.session_state["results"]              = results
            st.session_state["engines"]              = engines
            st.session_state["tech"]                 = {}
            st.session_state["audits"]               = {}
            st.session_state["selected_for_audit"]   = []
            st.session_state.pop("direct_url_ready", None)
            status.empty()

# ── STEP 2 (Search mode): Show Results + Tech Detection ──────────────────────
if "results" in st.session_state and st.session_state["results"]:
    results = st.session_state["results"]
    engines = st.session_state["engines"]

    st.subheader("Step 2 — Search Results")
    st.caption(f"Engines used: {' · '.join(engines)}")
    st.info(f"Found **{len(results)}** unique business websites after filtering directories & aggregators.")

    if st.button("🧪 Detect Tech Stack (CMS & Plugins)", use_container_width=True):
        prog   = st.progress(0)
        status = st.empty()
        tech   = {}
        for i, item in enumerate(results):
            url = item.get("source_url", "")
            status.text(f"Analysing {url}…")
            if url:
                tech[url] = detect_tech(url)
            prog.progress((i + 1) / len(results))
        st.session_state["tech"] = tech
        status.empty()
        prog.empty()
        st.success("Tech detection complete!")

    tech = st.session_state.get("tech", {})

    if "selected_for_audit" not in st.session_state:
        st.session_state["selected_for_audit"] = []

    all_urls = [item.get("source_url", "") for item in results if item.get("source_url")]

    # Track a "bulk action" flag so checkboxes re-render with correct values
    if "_select_action" not in st.session_state:
        st.session_state["_select_action"] = None

    sel_col1, sel_col2, _ = st.columns([1, 1, 4])
    with sel_col1:
        if st.button("☑ Select All", use_container_width=True):
            st.session_state["selected_for_audit"] = list(all_urls)
            st.session_state["_select_action"] = "all"
            st.rerun()
    with sel_col2:
        if st.button("☐ Deselect All", use_container_width=True):
            st.session_state["selected_for_audit"] = []
            st.session_state["_select_action"] = "none"
            st.rerun()

    selected = st.session_state["selected_for_audit"]

    for idx, item in enumerate(results):
        url  = item.get("source_url", "")
        name = item.get("business_name", url)
        snip = item.get("snippet", "")
        src  = item.get("source", "")
        t    = tech.get(url, {})
        already_audited = url in st.session_state.get("audits", {})

        with st.container():
            chk_col, info_col, btn_col = st.columns([0.5, 5, 1.5])

            with chk_col:
                # Use a key that changes after a bulk action so Streamlit re-renders
                # the checkbox with the updated value instead of keeping stale widget state
                action_suffix = st.session_state.get("_select_action", "")
                checked = st.checkbox(
                    f"Select {name}",
                    value=(url in selected),
                    key=f"chk_{idx}_{action_suffix}",
                    label_visibility="collapsed",
                )
                if checked and url not in selected:
                    selected.append(url)
                    st.session_state["selected_for_audit"] = selected
                    st.session_state["_select_action"] = None
                elif not checked and url in selected:
                    selected.remove(url)
                    st.session_state["selected_for_audit"] = selected
                    st.session_state["_select_action"] = None

            with info_col:
                audit_icon = " ✅" if already_audited else ""
                st.markdown(f"**{name}**{audit_icon}")
                st.caption(f"[{url}]({url})  ·  *{src}*")
                if snip:
                    st.caption(snip[:160])
                if t:
                    st.markdown(_render_tech_badges(t), unsafe_allow_html=True)

            with btn_col:
                if AUDIT_AVAILABLE:
                    btn_label = "✅ Re-audit" if already_audited else "🚀 Audit"
                    if st.button(btn_label, key=f"audit_{idx}", use_container_width=True):
                        # Remove previous result so UI doesn't show stale data during fetch
                        st.session_state["audits"].pop(url, None)
                        with st.spinner(f"Auditing {url}…"):
                            result = audit_website(url)
                        st.session_state["audits"][url] = result
                        st.rerun()

        st.divider()

    # ── Bulk Audit ────────────────────────────────────────────────────────────
    st.subheader("Audit Selected Sites")
    n_selected = len(selected)

    if n_selected == 0:
        st.info("☝ Tick the checkboxes above to choose which sites to audit, then click the button below.")
    else:
        st.success(f"**{n_selected}** site{'s' if n_selected != 1 else ''} selected for audit.")

    audit_selected_btn = st.button(
        f"🚀 Audit {n_selected} Selected Site{'s' if n_selected != 1 else ''}",
        type="primary",
        use_container_width=True,
        disabled=(n_selected == 0),
    )

    if audit_selected_btn and n_selected > 0:
        prog   = st.progress(0, text="Starting audit…")
        status = st.empty()
        batch  = [url for url in selected if url]
        for i, url in enumerate(batch):
            status.info(f"🔍 Auditing **{i+1}/{len(batch)}**: {url}")
            with st.spinner(f"Fetching & analysing {url}…"):
                result = audit_website(url)
            st.session_state["audits"][url] = result
            prog.progress((i + 1) / len(batch), text=f"Audited {i+1} of {len(batch)} sites…")
        status.empty()
        prog.empty()
        st.success(f"Audited {len(batch)} site{'s' if len(batch) != 1 else ''}!")
        st.rerun()

# ── STEP 3 / 4: Audit Results ─────────────────────────────────────────────────
audits = st.session_state.get("audits", {})
_direct_mode_results = audits and "results" not in st.session_state

if audits:
    step_label = "Step 4" if "results" in st.session_state else "Step 3"
    # In direct mode, tech + audit steps are already shown inline above,
    # so we only render the results card here.
    st.subheader(f"{step_label} — Audit Results")
    audit_list = list(audits.values())

    if not _direct_mode_results:
        scores    = [a.get("overall_score", 0) for a in audit_list]
        mc1, mc2 = st.columns(2)
        with mc1: st.metric("Sites Audited", len(audit_list))
        with mc2: st.metric("Avg Score",     f"{int(sum(scores)/len(scores)) if scores else 0}/100")

        only_poor = st.checkbox("Show only poor sites (< 60 score)")
        filtered  = [a for a in audit_list if not only_poor or a.get("overall_score", 100) < 60]
    else:
        filtered = audit_list

    for a in filtered:
        url   = a.get("url", "")
        score = a.get("overall_score", 0)
        bd    = a.get("breakdown", {})

        with st.expander(
            f"{'🟢' if score >= 70 else '🟡' if score >= 50 else '🔴'} "
            f"{url}  —  {score}/100",
            expanded=_direct_mode_results,
        ):
            st.markdown(
                f'<div style="height:8px;background:#eee;border-radius:4px;margin-bottom:12px;">'
                f'<div style="height:8px;width:{score}%;background:{_score_color(score)};border-radius:4px;"></div>'
                f'</div>', unsafe_allow_html=True
            )

            if bd:
                cols = st.columns(len(bd))
                for col, (cat, data) in zip(cols, bd.items()):
                    s = data.get("score", 0)
                    col.markdown(
                        f'<div style="text-align:center;">'
                        f'<div style="font-size:22px;font-weight:700;color:{_score_color(s)};">{s}</div>'
                        f'<div style="font-size:10px;color:#888;">{cat.upper()}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                st.divider()

            st.markdown("---")
            try:
                pdf_bytes = generate_audit_pdf(a, lang="en")
                safe      = url.replace("https://","").replace("http://","").replace("/","_").strip("_")
                st.download_button(
                    "⬇ Download Audit Report (PDF)",
                    data=pdf_bytes,
                    file_name=f"audit_{safe}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_{url}",
                )
            except Exception as e:
                st.warning(f"PDF generation failed: {e}")

    if not _direct_mode_results and len(filtered) > 1:
        st.subheader("Export All Results")
        writer = PdfWriter()
        for a in filtered:
            try:
                pdf_bytes = generate_audit_pdf(a, lang="en")
                writer.append(io.BytesIO(pdf_bytes))
            except Exception:
                pass
        if writer.pages:
            buf = io.BytesIO()
            writer.write(buf)
            buf.seek(0)
            st.download_button(
                "⬇ Download All Reports (PDF)",
                data=buf.read(),
                file_name="all_audit_reports.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.info("Run audits first to generate PDF reports.")

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Business Finder Pro · Multi-engine Search · Tech Detection · Audit · PDF Reports")