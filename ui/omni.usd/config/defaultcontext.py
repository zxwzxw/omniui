import omni.ext
import omni.usd
import carb


class Extension(omni.ext.IExt):
    def on_startup(self):
        fast_mode = carb.settings.get_settings().get("/app/startup/fast/mode")
        if not bool(fast_mode):
            omni.usd.create_context()

    def on_shutdown(self):
        omni.usd.destroy_context()
