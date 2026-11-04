"""A stand-in for BlueZ on a private D-Bus: org.bluez's ObjectManager answers GetManagedObjects with what a Pi sees
while it looks round (phones and earbuds sending manufacturer data, a{qv}; advertising data, a{yv}), so busctl's
real output can be checked. Usage: python3.12 fake_bluez.py ADDRESS [STATE.json]"""
import json
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

V = GLib.Variant
XML = """<node><interface name="org.freedesktop.DBus.ObjectManager">
<method name="GetManagedObjects"><arg type="a{oa{sa{sv}}}" direction="out"/></method>
</interface></node>"""
ADAPTER = "/org/bluez/hci0"


def device(addr, name=None, icon=None, paired=False, connected=False, rssi=None, maker=None, adv=None, alias=None):
    props = {"Address": V("s", addr), "AddressType": V("s", "public"), "Adapter": V("o", ADAPTER),
             "Paired": V("b", paired), "Bonded": V("b", paired), "Trusted": V("b", paired),
             "Blocked": V("b", False), "LegacyPairing": V("b", False), "Connected": V("b", connected),
             "UUIDs": V("as", ["0000110b-0000-1000-8000-00805f9b34fb"]), "ServicesResolved": V("b", connected),
             "Alias": V("s", alias or name or addr.replace(":", "-"))}
    if name is not None:
        props["Name"] = V("s", name)
    if icon:
        props["Icon"] = V("s", icon)
    if rssi is not None:
        props["RSSI"] = V("n", rssi)
        props["TxPower"] = V("n", 4)
    if maker:
        props["ManufacturerData"] = V("a{qv}", {k: V("ay", bytes(v)) for k, v in maker.items()})
    if adv:
        props["AdvertisingData"] = V("a{yv}", {k: V("ay", bytes(v)) for k, v in adv.items()})
        props["AdvertisingFlags"] = V("ay", bytes([0x06]))
    props["ServiceData"] = V("a{sv}", {"0000fe2c-0000-1000-8000-00805f9b34fb": V("ay", bytes([0, 1]))})
    path = ADAPTER + "/dev_" + addr.replace(":", "_")
    return path, {"org.freedesktop.DBus.Introspectable": {}, "org.bluez.Device1": props,
                  "org.freedesktop.DBus.Properties": {}}


def objects(state):
    objs = {"/org/bluez": {"org.freedesktop.DBus.Introspectable": {}, "org.bluez.AgentManager1": {},
                           "org.bluez.ProfileManager1": {}},
            ADAPTER: {"org.freedesktop.DBus.Introspectable": {},
                      "org.bluez.Adapter1": {"Address": V("s", "B8:27:EB:00:00:01"), "AddressType": V("s", "public"),
                                             "Name": V("s", "pitato"), "Alias": V("s", "pitato"),
                                             "Class": V("u", 0x6c0000), "Powered": V("b", state.get("on", True)),
                                             "Discoverable": V("b", False), "Pairable": V("b", True),
                                             "Discovering": V("b", state.get("looking", True)),
                                             "UUIDs": V("as", []), "Modalias": V("s", "usb:v1D6Bp0246d0542"),
                                             "Roles": V("as", ["central", "peripheral"])},
                      "org.bluez.GattManager1": {}, "org.bluez.Media1": {},
                      "org.bluez.LEAdvertisingManager1": {"ActiveInstances": V("y", 0),
                                                          "SupportedInstances": V("y", 5),
                                                          "SupportedIncludes": V("as", ["tx-power"])}}}
    for d in state.get("devices", []):
        path, o = device(**d)
        objs[path] = o
    return objs


def main():
    address = sys.argv[1]
    state_file = sys.argv[2] if len(sys.argv) > 2 else None

    def state():
        if state_file:
            with open(state_file) as f:
                return json.load(f)
        return {"devices": [
            {"addr": "DC:2C:26:00:00:20", "name": "BBQ20KBD", "icon": "input-keyboard", "paired": True,
             "connected": True},
            {"addr": "4C:87:5D:11:22:33", "name": "Pixel 8", "icon": "phone", "rssi": -58,
             "maker": {224: [1, 2, 3, 4]}},
            {"addr": "70:F9:4A:44:55:66", "name": "Sam’s AirPods", "icon": "audio-headphones", "rssi": -71,
             "maker": {76: [0x07, 0x19, 0x01]}, "adv": {0xff: [0x4c, 0x00, 0x07]}},
            {"addr": "E4:17:D8:77:88:99", "name": 'My "Keys" \\ Pad\tX', "rssi": -80, "maker": {0x0059: []}},
            {"addr": "11:22:33:44:55:66", "rssi": -90, "maker": {6: [9, 9]}},      # (a beacon: no name)
        ]}

    def on_call(conn, sender, path, iface, method, params, invocation):
        invocation.return_value(V("(a{oa{sa{sv}}})", (objects(state()),)))

    conn = Gio.DBusConnection.new_for_address_sync(
        address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None, None)
    info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
    conn.register_object("/", info, on_call, None, None)
    conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName",
                   V("(su)", ("org.bluez", 4)), None, Gio.DBusCallFlags.NONE, -1, None)
    print("ready", flush=True)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
