"""Card loading: own static path, dashboard resource, versions (needs the homeassistant package)."""
import asyncio
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from aiohttp import web  # noqa: E402

from custom_components.smart_heating import card  # noqa: E402
from custom_components.smart_heating.const import VERSION  # noqa: E402


def test_versions_match():
    manifest = json.loads((ROOT / "custom_components/smart_heating/manifest.json").read_text())["version"]
    js = re.search(r'const CARD_VERSION = "([^"]+)"', card.SOURCE.read_text()).group(1)
    readme = re.search(r"^Version (\S+)\. ", (ROOT / "README.md").read_text(), re.M).group(1)
    assert manifest == VERSION == js == readme


class Resources:
    """Stand-in for HA's dashboard resource storage collection."""

    def __init__(self, items=()):
        self.items = {str(i): dict(it, id=str(i)) for i, it in enumerate(items)}
        self.loaded = False

    async def async_load(self):
        self.loaded = True

    def async_items(self):
        return list(self.items.values())

    async def async_create_item(self, data):
        rid = f"new{len(self.items)}"
        self.items[rid] = {"id": rid, "type": data["res_type"], "url": data["url"]}

    async def async_update_item(self, rid, data):
        self.items[rid].update(type=data["res_type"], url=data["url"])

    async def async_delete_item(self, rid):
        del self.items[rid]


def test_sync_resource():
    other = {"type": "module", "url": "/hacsfiles/button-card/button-card.js?hacstag=1"}
    res = Resources([other])
    asyncio.run(card.sync_resource(res, "/smart_heating/smart-heating-card.js?v=1"))
    assert res.loaded
    assert sorted(r["url"] for r in res.async_items()) == sorted([other["url"], "/smart_heating/smart-heating-card.js?v=1"])
    # An update moves it to the new version; duplicates (also hand-made ones) go.
    res = Resources([other, {"type": "module", "url": "/smart_heating/smart-heating-card.js?v=0.13.0"},
                     {"type": "js", "url": "/local/smart_heating/smart-heating-card.js"}])
    asyncio.run(card.sync_resource(res, "/smart_heating/smart-heating-card.js?v=2"))
    ours = [r for r in res.async_items() if "smart-heating" in r["url"]]
    assert ours == [{"id": "1", "type": "module", "url": "/smart_heating/smart-heating-card.js?v=2"}]
    assert other["url"] in [r["url"] for r in res.async_items()]


def _hass(tmp_path, resources):
    router = web.UrlDispatcher()
    extra = SimpleNamespace(urls=set())
    extra.add, extra.remove = extra.urls.add, extra.urls.discard

    async def register_static(paths):
        for p in paths:
            router.register_resource(web.StaticResource(p.url_path, str(Path(p.path).parent)))

    async def executor(func, *args):
        return func(*args)

    return SimpleNamespace(
        data={"lovelace": SimpleNamespace(resources=resources), "frontend_extra_module_url": extra},
        http=SimpleNamespace(app=SimpleNamespace(router=router), async_register_static_paths=register_static),
        config=SimpleNamespace(path=lambda *p: str(tmp_path.joinpath(*p))),
        async_add_executor_job=executor,
    ), extra


def test_register_update_remove(tmp_path):
    # A resource left by 0.14.1 to 0.15.3 (served from the www copy) is pointed back at the integration's own path.
    res = Resources([{"type": "module", "url": "/local/smart_heating/smart-heating-card.js?v=0.15.3"}])
    hass, extra = _hass(tmp_path, res)
    want = f"/smart_heating/smart-heating-card.js?v={VERSION}"
    asyncio.run(card.async_register_card(hass))
    assert [r["url"] for r in res.async_items()] == [want], "resource follows the installed version, own path"
    assert extra.urls == {want}, "same URL as the resource: the browser loads it once"
    assert not (tmp_path / "www").exists(), "nothing written to the user's www folder"
    asyncio.run(card.async_register_card(hass))
    assert len(res.async_items()) == 1 and extra.urls == {want}
    asyncio.run(card.async_remove_card(hass))
    assert res.async_items() == [] and extra.urls == set()


def test_register_yaml_resources(tmp_path):
    # Resources in YAML: no collection to write to, the extra module still loads the card.
    hass, extra = _hass(tmp_path, SimpleNamespace())
    asyncio.run(card.async_register_card(hass))
    assert extra.urls == {f"/smart_heating/smart-heating-card.js?v={VERSION}"}
