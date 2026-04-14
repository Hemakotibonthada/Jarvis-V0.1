"""
Home Automation — Controls smart home devices via MQTT or HTTP.
Works offline with local MQTT broker (e.g., Mosquitto).
"""

import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger("Jarvis.Home")


class HomeAutomation:
    """Manages smart home devices via MQTT."""

    def __init__(self, config: dict):
        self.mqtt_broker = config.get("mqtt_broker", "localhost")
        self.mqtt_port = config.get("mqtt_port", 1883)
        self._client = None
        self._devices = {
            "living_room_light": {"topic": "home/living_room/light", "state": False},
            "bedroom_light": {"topic": "home/bedroom/light", "state": False},
            "kitchen_light": {"topic": "home/kitchen/light", "state": False},
            "fan": {"topic": "home/living_room/fan", "state": False},
        }
        self._connect_mqtt()

    def _connect_mqtt(self):
        try:
            import asyncio_mqtt
            logger.info(f"MQTT broker configured: {self.mqtt_broker}:{self.mqtt_port}")
        except ImportError:
            logger.warning("asyncio-mqtt not installed. Home automation limited.")

    async def handle(self, intent: str, text: str) -> Optional[dict]:
        text_lower = text.lower()

        if intent == "home_lights_on":
            device = self._find_device(text_lower)
            if device:
                return await self._set_device(device, True)
            # Turn on all lights
            return await self._set_all_lights(True)

        elif intent == "home_lights_off":
            device = self._find_device(text_lower)
            if device:
                return await self._set_device(device, False)
            return await self._set_all_lights(False)

        return None

    async def _set_device(self, device_name: str, state: bool) -> dict:
        if device_name not in self._devices:
            return {"response": f"I don't recognize the device '{device_name}'."}

        device = self._devices[device_name]
        device["state"] = state
        state_str = "on" if state else "off"

        # Publish MQTT message
        await self._publish(device["topic"], json.dumps({"state": state_str}))

        friendly_name = device_name.replace("_", " ")
        return {
            "response": f"The {friendly_name} has been turned {state_str}.",
            "params": {"device": device_name, "state": state_str},
        }

    async def _set_all_lights(self, state: bool) -> dict:
        state_str = "on" if state else "off"
        for name, device in self._devices.items():
            if "light" in name:
                device["state"] = state
                await self._publish(device["topic"], json.dumps({"state": state_str}))

        return {
            "response": f"All lights have been turned {state_str}.",
            "params": {"action": f"all_lights_{state_str}"},
        }

    async def _publish(self, topic: str, payload: str):
        try:
            import asyncio_mqtt
            async with asyncio_mqtt.Client(self.mqtt_broker, self.mqtt_port) as client:
                await client.publish(topic, payload.encode())
                logger.info(f"MQTT published: {topic} = {payload}")
        except Exception as e:
            logger.debug(f"MQTT publish skipped (broker not available): {e}")

    def _find_device(self, text: str) -> Optional[str]:
        for device_name in self._devices:
            friendly = device_name.replace("_", " ")
            if friendly in text:
                return device_name

        # Partial match
        if "living" in text or "room" in text:
            return "living_room_light"
        if "bed" in text:
            return "bedroom_light"
        if "kitchen" in text:
            return "kitchen_light"
        if "fan" in text:
            return "fan"

        return None

    def get_status(self) -> dict:
        return {
            name: {"state": "on" if d["state"] else "off"}
            for name, d in self._devices.items()
        }
