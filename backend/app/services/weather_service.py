"""Weather service using Amap (高德地图) API.

Provides two tools:
1. reverse_geocode: 经纬度 → 行政区划代码 + 地址描述
2. get_weather: 行政区划代码 → 天气/温度/湿度

Plus a one-stop function: get_location_weather(latitude, longitude) → location + weather
"""

from __future__ import annotations

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

# Amap API endpoints
_GEOCODE_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


async def reverse_geocode(latitude: float, longitude: float) -> dict:
    """将经纬度转为行政区划代码和地址描述。

    高德逆地理编码API: https://restapi.amap.com/v3/geocode/regeo
    参数: key, location(经度,纬度)
    返回: {"adcode": "110105", "province": "北京", "city": "北京市", "district": "朝阳区",
            "formatted_address": "北京市朝阳区..."}
    """
    amap_key = settings.amap.api_key
    if not amap_key:
        logger.warning("amap_api_key_not_configured")
        return {}

    location = f"{longitude},{latitude}"  # 高德格式：经度,纬度
    params = {"key": amap_key, "location": location}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_GEOCODE_REGEO_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "1":
            logger.error("amap_reverse_geocode_failed", info=data.get("info", ""))
            return {}

        regeo = data.get("regeocode", {})
        addr_component = regeo.get("addressComponent", {})
        return {
            "adcode": addr_component.get("adcode", ""),
            "province": addr_component.get("province", ""),
            "city": addr_component.get("city", ""),
            "district": addr_component.get("district", ""),
            "formatted_address": regeo.get("formatted_address", ""),
        }
    except Exception as e:
        logger.error("amap_reverse_geocode_error", error=str(e))
        return {}


async def get_weather(adcode: str) -> dict:
    """调用高德地图天气查询API，返回天气/温度/湿度。

    高德天气API: https://restapi.amap.com/v3/weather/weatherInfo
    参数: key, city(adcode), extensions=base(实况天气)
    返回: {"weather": "晴", "temperature": "25", "humidity": "65"}
    """
    amap_key = settings.amap.api_key
    if not amap_key:
        logger.warning("amap_api_key_not_configured")
        return {}

    params = {"key": amap_key, "city": adcode, "extensions": "base"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_WEATHER_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "1":
            logger.error("amap_weather_failed", info=data.get("info", ""))
            return {}

        lives = data.get("lives", [])
        if not lives:
            return {}

        live = lives[0]
        return {
            "weather": live.get("weather", ""),
            "temperature": live.get("temperature", ""),
            "humidity": live.get("humidity", ""),
        }
    except Exception as e:
        logger.error("amap_weather_error", error=str(e))
        return {}


async def get_location_weather(latitude: float, longitude: float) -> dict:
    """一站式：经纬度 → 逆地理编码获取adcode → 查询天气。

    返回: {"location": "北京市朝阳区", "weather": "晴", "temperature": "25", "humidity": "65",
            "province": "北京", "city": "北京市", "district": "朝阳区"}
    """
    # Step 1: Reverse geocode
    geo = await reverse_geocode(latitude, longitude)
    if not geo:
        return {"location": "", "weather": "", "temperature": "", "humidity": ""}

    # Build location display string
    province = geo.get("province", "")
    city = geo.get("city", "")
    district = geo.get("district", "")
    # 高德对直辖市返回 city=""，此时用 province
    location_display = f"{city or province}{district}" if district else (city or province)

    # Step 2: Get weather
    adcode = geo.get("adcode", "")
    weather_data = {}
    if adcode:
        weather_data = await get_weather(adcode)

    return {
        "location": location_display,
        "weather": weather_data.get("weather", ""),
        "temperature": weather_data.get("temperature", ""),
        "humidity": weather_data.get("humidity", ""),
        "province": province,
        "city": city,
        "district": district,
    }
