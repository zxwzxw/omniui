import asyncio

import omni.kit.test


from pxr import Tf


class TestUsdBootstrap(omni.kit.test.AsyncTestCase):
    # Verifies that TfEnvSettings are bootstrapped in the correct order--
    # see https://gitlab-master.nvidia.com/carbon/Graphene/merge_requests/3115#note_5019170
    async def test_tf_env_settings(self):
        self.assertEqual(Tf.GetEnvSetting("USDIMAGING_DISABLE_CAMERA_ADAPTER"), 0)
        self.assertEqual(Tf.GetEnvSetting("USDIMAGING_ENABLE_SPARSE_LIGHT_UPDATES"), 1)
        self.assertEqual(Tf.GetEnvSetting("USDIMAGING_ENABLE_NESTED_GPRIMS"), 1)
        self.assertEqual(Tf.GetEnvSetting("USDGEOM_XFORMCOMMONAPI_ALLOW_DOUBLES"), 1)
        self.assertEqual(Tf.GetEnvSetting("USDIMAGING_ALLOW_UNREGISTERED_SHADER_IDS"), 1)
        self.assertEqual(Tf.GetEnvSetting("PCP_DISABLE_TIME_SCALING_BY_LAYER_TCPS"), 0)

        # Disabled until all cases found in OM-9409 are addressed
        self.assertEqual(Tf.GetEnvSetting("USDIMAGING_UNKNOWN_PROPERTIES_ARE_CLEAN"), 0)

        mdl_string = r'AperturePBR.mdl,AperturePBR_Opacity.mdl,AperturePBR_ThinOpaque.mdl,AperturePBR_ThinTranslucent.mdl,AperturePBR_Translucent.mdl,OmniGlass.mdl,OmniGlass_Opacity.mdl,OmniHair.mdl,OmniHairPresets.mdl,OmniPBR.mdl,OmniPBR_ClearCoat.mdl,OmniPBR_ClearCoat_Opacity.mdl,OmniPBR_Opacity.mdl,OmniSurface.mdl,OmniSurfaceBlend.mdl,OmniSurfaceLite.mdl,OmniSurfacePresets.mdl,adobe/anisotropy.mdl,adobe/annotations.mdl,adobe/convert.mdl,adobe/materials.mdl,adobe/mtl.mdl,adobe/util.mdl,adobe/volume.mdl,alg/base/annotations.mdl,alg/base/core.mdl,alg/base/normalmapping.mdl,alg/materials/blinn.mdl,alg/materials/designer.mdl,alg/materials/lambert.mdl,alg/materials/lights.mdl,alg/materials/physically_metallic_roughness.mdl,alg/materials/physically_specular_glossiness.mdl,alg/materials/asm/standard_scatter.mdl,alg/materials/designer/blinn.mdl,alg/materials/designer/lambert.mdl,alg/materials/designer/lights.mdl,alg/materials/designer/pbr.mdl,alg/materials/designer/skin.mdl,alg/materials/designer/legacy/physically_metallic_roughness.mdl,alg/materials/designer/legacy/physically_metallic_roughness_coated.mdl,alg/materials/designer/legacy/physically_metallic_roughness_sss.mdl,alg/materials/designer/legacy/physically_specular_glossiness.mdl,gltf/pbr.mdl,materialx/cm.mdl,materialx/core.mdl,materialx/hsv.mdl,materialx/noise.mdl,materialx/pbrlib.mdl,materialx/sampling.mdl,materialx/stdlib.mdl,materialx/swizzle.mdl,nvidia/aux_definitions.mdl,nvidia/core_definitions.mdl,nvidia/support_definitions.mdl,OmniSurface/OmniHairBase.mdl,OmniSurface/OmniImage.mdl,OmniSurface/OmniShared.mdl,OmniSurface/OmniSurfaceBase.mdl,OmniSurface/OmniSurfaceBlendBase.mdl,OmniSurface/OmniSurfaceLiteBase.mdl,OmniUe4Base.mdl,OmniUe4Function.mdl,OmniUe4FunctionExtension17.mdl,OmniUe4Subsurface.mdl,OmniUe4Translucent.mdl,OmniVolumeDensity.mdl,OmniVolumeNoise.mdl,ad_3dsmax_maps.mdl,ad_3dsmax_materials.mdl,vray_maps.mdl,vray_materials.mdl,DebugWhite.mdl,DebugWhiteEmissive.mdl,Default.mdl,MdlStates.mdl,UsdPreviewSurface.mdl,architectural.mdl,environment.mdl,omni_light.mdl'
        mdl_list = mdl_string.split(",").sort()

        env_mdls = Tf.GetEnvSetting("OMNI_USD_RESOLVER_MDL_BUILTIN_PATHS").split(",").sort()
        self.assertEqual(mdl_list, env_mdls)
        

