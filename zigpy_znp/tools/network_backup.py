import sys
import json
import typing
import asyncio
import logging
import argparse
import datetime

import zigpy_znp
from zigpy_znp.api import ZNP
from zigpy_znp.types.nvids import OsalNvIds
from zigpy_znp.tools.common import setup_parser
from zigpy_znp.znp.security import read_devices, read_tc_frame_counter
from zigpy_znp.tools.energy_scan import channels_from_channel_mask
from zigpy_znp.zigbee.application import ControllerApplication

LOGGER = logging.getLogger(__name__)


async def backup_network(radio_path: str) -> typing.Dict[str, typing.Any]:
    znp = ZNP(ControllerApplication.SCHEMA({"device": {"path": radio_path}}))
    await znp.connect()
    await znp.load_network_info()

    devices = []

    for device in await read_devices(znp):
        obj = {
            "nwk": device.nwk.serialize()[::-1].hex(),
            "ieee": device.ieee.serialize()[::-1].hex(),
        }

        if device.aps_link_key:
            obj["link_key"] = {
                "tx_counter": device.tx_counter,
                "rx_counter": device.rx_counter,
                "key": device.aps_link_key.serialize().hex(),
            }

        devices.append(obj)

    devices.sort(key=lambda d: d["ieee"])

    now = datetime.datetime.now().astimezone()

    obj = {
        "metadata": {
            "version": 1,
            "format": "zigpy/open-coordinator-backup",
            "source": f"zigpy-znp@{zigpy_znp.__version__}",
            "internal": {
                "creation_time": now.isoformat(timespec="seconds"),
                "zstack": {
                    "version": znp.version,
                },
            },
        },
        "coordinator_ieee": znp.network_info.ieee.serialize()[::-1].hex(),
        "pan_id": znp.network_info.pan_id.serialize()[::-1].hex(),
        "extended_pan_id": znp.network_info.extended_pan_id.serialize()[::-1].hex(),
        "nwk_update_id": znp.network_info.nwk_update_id,
        "security_level": znp.network_info.security_level,
        "channel": znp.network_info.channel,
        "channel_mask": list(channels_from_channel_mask(znp.network_info.channels)),
        "network_key": {
            "key": znp.network_info.network_key.serialize().hex(),
            "sequence_number": znp.network_info.network_key_seq,
            "frame_counter": await read_tc_frame_counter(znp),
        },
        "devices": devices,
    }

    if znp.version > 1.2:
        tclk_seed = await znp.nvram.osal_read(OsalNvIds.TCLK_SEED)
        LOGGER.info("TCLK seed: %s", tclk_seed.hex())

        obj["stack_specific"] = {"zstack": {"tclk_seed": tclk_seed.hex()}}

    znp.close()

    return obj


async def main(argv):
    parser = setup_parser("Backup adapter network settings")
    parser.add_argument(
        "--output", "-o", type=argparse.FileType("w"), help="Output file", default="-"
    )
    args = parser.parse_args(argv)

    backup_obj = await backup_network(
        radio_path=args.serial,
    )

    args.output.write(json.dumps(backup_obj, indent=4))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))  # pragma: no cover
