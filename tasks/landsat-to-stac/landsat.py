import pystac

from dateutil.parser import parse
from pystac.extensions.eo import Band
from pystac.extensions.base import ItemExtension, ExtendedObject, ExtensionDefinition


class LandsatExt(ItemExtension):
    def __init__(self, item):
        self.item = item

    @classmethod
    def from_item(cls, item):
        return LandsatExt(item)

    @classmethod
    def _object_links(cls):
        return []

    def apply(self, scene_id=None, processing_level=None,
              collection_number=None, collection_category=None,
              cloud_cover_land=None, wrs_path=None, wrs_row=None):
        """Applies landsat extension properties to the extended Item.
        """
        self.scene_id = scene_id
        self.processing_level = processing_level
        self.collection_number = collection_number
        self.collection_category = collection_category
        self.cloud_cover_land = cloud_cover_land
        self.wrs_path = wrs_path
        self.wrs_row = wrs_row

    @property
    def scene_id(self):
        """ Landsat Scene ID """
        return self.item.properties.get('landsat:scene_id')

    @scene_id.setter
    def scene_id(self, val):
        self.item.properties['landsat:scene_id'] = val

    @property
    def processing_level(self):
        """ Landsat Processing PROCESSING_LEVEL """
        return self.item.properties.get('landsat:processing_level')

    @processing_level.setter
    def processing_level(self, val):
        self.item.properties['landsat:processing_level'] = val

    @property
    def collection_number(self):
        """ Landsat COLLECTION_NUMBER """
        return self.item.properties.get('landsat:collection_number')

    @collection_number.setter
    def collection_number(self, val):
        self.item.properties['landsat:collection_number'] = val

    @property
    def collection_category(self):
        """ Landsat COLLECTION_CATEGORY """
        return self.item.properties.get('landsat:collection_category')

    @collection_category.setter
    def collection_category(self, val):
        self.item.properties['landsat:collection_category'] = val

    @property
    def cloud_cover_land(self):
        """ Landsat CLOUD_COVER_LAND """
        return self.item.properties.get('landsat:cloud_cover_land')

    @cloud_cover_land.setter
    def cloud_cover_land(self, val):
        self.item.properties['landsat:cloud_cover_land'] = val

    '''
    @property
    def wrs_type(self):
        """ Landsat WRS_TYPE """
        return self.item.properties.get('landsat:wrs_type')

    @wrs_type.setter
    def wrs_type(self, val):
        self.item.properties['landsat:wrs_type'] = val
    '''

    @property
    def wrs_path(self):
        """ Landsat WRS_PATH """
        return self.item.properties.get('landsat:wrs_path')

    @wrs_path.setter
    def wrs_path(self, val):
        self.item.properties['landsat:wrs_path'] = val

    @property
    def wrs_row(self):
        """ Landsat WRS_ROW """
        return self.item.properties.get('landsat:wrs_row')

    @wrs_row.setter
    def wrs_row(self, val):
        self.item.properties['landsat:wrs_row'] = val

landsat_def = ExtensionDefinition('landsat', [ExtendedObject(pystac.Item, LandsatExt)])
pystac.STAC_EXTENSIONS.add_extension(landsat_def)


band_info = {
    'B1': {
        'band': Band.create(name="B1", common_name="coastal", center_wavelength=0.48, full_width_half_max=0.02),
        'gsd': 30.0
    },
    'B2': {
        'band': Band.create(name="B2", common_name="blue", center_wavelength=0.44, full_width_half_max=0.06),
        'gsd': 30.0
    },
    'B3': {
        'band': Band.create(name="B3", common_name="green", center_wavelength=0.56, full_width_half_max=0.06),
        'gsd': 30.0
    },
    'B4': {
        'band': Band.create(name="B4", common_name="red", center_wavelength=0.65, full_width_half_max=0.04),
        'gsd': 30.0
    },
    'B5': {
        'band': Band.create(name="B5", common_name="nir", center_wavelength=0.86, full_width_half_max=0.03),
        'gsd': 30.0
    },
    'B6': {
        'band': Band.create(name="B6", common_name="swir16", center_wavelength=1.6, full_width_half_max=0.08),
        'gsd': 30.0
    },
    'B7': {
        'band': Band.create(name="B7", common_name="swir22", center_wavelength=2.2, full_width_half_max=0.2),
        'gsd': 30.0
    },
    'B8': {
        'band': Band.create(name="B8", common_name="pan", center_wavelength=0.59, full_width_half_max=0.18),
        'gsd': 15.0
    },
    'B9': {
        'band': Band.create(name="B9", common_name="cirrus", center_wavelength=1.37, full_width_half_max=0.02),
        'gsd': 30.0
    },
    'B10': {
        'band': Band.create(name="B10", common_name="lwir11", center_wavelength=10.9, full_width_half_max=0.8),
        'gsd': 100.0
    },
    'B11': {
        'band': Band.create(name="B11", common_name="lwir12", center_wavelength=12.0, full_width_half_max=1.0),
        'gsd': 100.0
    }
}



def mtl_to_json(mtl_text):
    """ Convert Landsat MTL file to dictionary of metadata values """
    mtl = {}
    for line in mtl_text.split('\n'):
        meta = line.replace('\"', "").strip().split('=')
        if len(meta) > 1:
            key = meta[0].strip()
            item = meta[1].strip()
            if key != "GROUP" and key != "END_GROUP":
                mtl[key] = item
    return mtl


def get_datetime(metadata):
    return parse('%sT%s' % (metadata['DATE_ACQUIRED'], metadata['SCENE_CENTER_TIME']))


def get_bbox(metadata):
    coords = [[
        [float(metadata['CORNER_UL_LON_PRODUCT']), float(metadata['CORNER_UL_LAT_PRODUCT'])],
        [float(metadata['CORNER_UR_LON_PRODUCT']), float(metadata['CORNER_UR_LAT_PRODUCT'])],
        [float(metadata['CORNER_LR_LON_PRODUCT']), float(metadata['CORNER_LR_LAT_PRODUCT'])],
        [float(metadata['CORNER_LL_LON_PRODUCT']), float(metadata['CORNER_LL_LAT_PRODUCT'])],
        [float(metadata['CORNER_UL_LON_PRODUCT']), float(metadata['CORNER_UL_LAT_PRODUCT'])]
    ]]
    lats = [c[1] for c in coords[0]]
    lons = [c[0] for c in coords[0]]
    return [min(lons), min(lats), max(lons), max(lats)]


def get_geometry(ang_text, bbox):
    sz = []
    coords = []
    for line in ang_text.split('\n'):
        if 'BAND01_NUM_L1T_LINES' in line or 'BAND01_NUM_L1T_SAMPS' in line:
            sz.append(float(line.split('=')[1]))
        if 'BAND01_L1T_IMAGE_CORNER_LINES' in line or 'BAND01_L1T_IMAGE_CORNER_SAMPS' in line:
            coords.append([float(l) for l in line.split('=')[1].strip().strip('()').split(',')])
        if len(coords) == 2:
            break
    dlon = bbox[2] - bbox[0]
    dlat = bbox[3] - bbox[1]
    lons = [c/sz[1] * dlon + bbox[0] for c in coords[1]]
    lats = [((sz[0] - c)/sz[0]) * dlat + bbox[1] for c in coords[0]]
    coordinates = [[
        [lons[0], lats[0]], [lons[1], lats[1]], [lons[2], lats[2]], [lons[3], lats[3]], [lons[0], lats[0]]
    ]]
    
    return {'type': 'Polygon', 'coordinates': coordinates}


def get_epsg(metadata, min_lat, max_lat):
    if 'UTM_ZONE' in metadata:
        center_lat = (min_lat + max_lat)/2.0
        return int(('326' if center_lat > 0 else '327') + metadata['UTM_ZONE'])
    else:
        return None


def get_view_info(metadata):
    return { 'sun_azimuth': float(metadata['SUN_AZIMUTH']),
             'sun_elevation': float(metadata['SUN_ELEVATION']),
             'off_nadir': float(metadata['ROLL_ANGLE']) }


def get_landsat_info(metadata):
    return {
        'scene_id': metadata['LANDSAT_SCENE_ID'],
        'processing_level': metadata['DATA_TYPE'],
        'collection_number': metadata['COLLECTION_NUMBER'],
        'collection_category': metadata['COLLECTION_CATEGORY'],
        'cloud_cover_land': float(metadata['CLOUD_COVER_LAND']),
        'wrs_path': metadata['WRS_PATH'],
        'wrs_row': metadata['WRS_ROW']
    }


def add_assets(item, base_url):       
    # add non-band assets
    item.add_asset(
        'thumbnail',
        pystac.Asset(
            title = 'Thumbnail',
            href = base_url + '_thumb_large.jpg',
            media_type = pystac.MediaType.JPEG,
            roles = ['thumbnail']
        )
    )
    item.add_asset(
        'index',
        pystac.Asset(
            title = 'HTML Page',
            href = base_url+'_index.html',
            media_type = 'application/html'
        )   
    )
    item.add_asset(
        'ANG',
        pystac.Asset(
            title='ANG Metadata',
            href = base_url + '_ANG.txt',
            media_type='text/plain',
            roles=['metadata']
        )
    )
    item.add_asset(
        'MTL',
        pystac.Asset(
            title = 'MTL Metadata',
            href = base_url + '_MTL.txt',
            media_type = 'text/plain',
            roles = ['metadata']
        )
    )
    item.add_asset(
        'BQA',
        pystac.Asset(
            title = 'Quality Band',
            href = base_url + '_BQA.TIF',
            media_type = pystac.MediaType.GEOTIFF,
            roles = ['quality']
        )
    )

    # Add bands
    for band_id, info in band_info.items():
        band_url = f"{base_url}_{band_id}.TIF"
        asset = pystac.Asset(href=band_url, media_type=pystac.MediaType.COG)
        bands = [info['band']]
        item.ext.eo.set_bands(bands, asset)
        item.add_asset(band_id, asset)
        
        # If this asset has a different GSD than the item, set it on the asset
        if info['gsd'] != item.common_metadata.gsd:
            item.common_metadata.set_gsd(info['gsd'], asset)