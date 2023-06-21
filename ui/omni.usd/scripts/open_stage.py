"""Script to open USD stage."""

import carb
import argparse
import omni.usd
import asyncio
import omni.client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to USD stage.")

    try:
        options = parser.parse_args()
    except Exception as e:
        carb.log_error(str(e))
        return

    asyncio.ensure_future(open_stage_async(options.path))

async def open_stage_async(path: str):
    result, _ = await omni.client.stat_async(path)
    if result == omni.client.Result.OK:
        omni.usd.get_context().open_stage_with_callback(path, None)
        return

    broken_url = omni.client.break_url(path)
    if broken_url.scheme == 'omniverse':
        # Attempt to connect to nucleus server before opening stage
        try:
            from omni.kit.widget.nucleus_connector import get_nucleus_connector
            nucleus_connector = get_nucleus_connector()
        except Exception:
            carb.log_warn(f"Open stage: Could not import Nucleus connector.")
            return
        server_url = omni.client.make_url(scheme='omniverse', host=broken_url.host)
        nucleus_connector.connect(broken_url.host, server_url, 
            on_success_fn=lambda *_: omni.usd.get_context().open_stage_with_callback(path, None),
            on_failed_fn=lambda *_: carb.log_error(f"Open stage: Failed to connect to server '{server_url}'.")
        )
    else:
        carb.log_warn(f"Open stage: Could not open non-existent url '{path}'.")


main()
