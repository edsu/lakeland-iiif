#!/usr/bin/env python

import os
import re
import iiif
import json
import hashlib
import logging
import argparse
import requests

from os.path import join
from string import punctuation
from iiif_prezi.factory import ManifestFactory

def main(omeka_url, iiif_url):
    mf = ManifestFactory()
    mf.set_base_prezi_uri(iiif_url)
    mf.set_iiif_image_info(2.0, 0)

    for item in omeka_images(omeka_url):
        meta = get_metadata(item)
        print(meta['title'])

        manifest = mf.manifest(label=meta['title'])
        manifest.set_metadata(meta)

        sequence = manifest.sequence()
        page_num = 0

        for file in omeka_files(omeka_url, item['id']):
            image_path = download_image(file['file_urls']['original'])

            try:
                image_info = generate_tiles(image_path, item['id'], iiif_url)
            except iiif.error.IIIFError:
                continue
     
            page_num += 1
            canvas = sequence.canvas(
                ident="page-%s" % page_num, 
                label="Page %s" % page_num
            )
            canvas.thumbnail = get_thumbnail(image_info)

            anno = canvas.annotation()
            image = anno.image(image_info['@id'], iiif=True)
            image.height = image_info['height']
            image.width = image_info['width']

            canvas.height = image.height
            canvas.width = image.width
   
        if page_num > 0:
            write_manifest(manifest, item['id'])

    # write the last one


def omeka_images(omeka_url):
    url = omeka_url + "/api/items"
    page = 1
    while True:
        items = requests.get(url, {"page": page}).json()
        if len(items) == 0:
            break
        for item in items:
            if 'item_type' in item and item['item_type'] and item['item_type']['name'] == 'Still Image':
                yield item
        page += 1

def omeka_files(omeka_url, item_id):
    url = omeka_url + "/api/files"
    page = 1
    while True:
        resp = requests.get(url, {"item": item_id, "page": page})
        if not resp.content:
            return
        files = resp.json()
        if len(files) == 0:
            break
        for file in files:
            yield file
        page += 1

def id(path):
    m = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            m.update(chunk)
    return m.hexdigest()


def get_image_url(id):
    return "%s/images/tiles/%s" % (config['hostname'], id)


def generate_tiles(image_path, item_id, iiif_url):
    image_id = md5(image_path)
    image_url = "%s/images/tiles/%s" % (iiif_url, image_id)
    local_path = os.path.join(".", "images", "tiles", image_id)

    if not os.path.isdir(local_path):
        tiles = iiif.static.IIIFStatic(src=image_path, dst="./images/tiles",
                tilesize=1024, api_version="2.0")
        tiles.generate(image_path, identifier=image_id)

    info_json = os.path.join(local_path, "info.json")
    info = json.load(open(info_json))
    info['@id'] = image_url
    json.dump(info, open(info_json, "w"), indent=2)
    return info

def write_manifest(manifest, item_id):
    with open("manifests/%s.json" % item_id, "w") as fh:
        fh.write(manifest.toString(compact=False))

    # add the manifest to our index of manifests
    # TODO: make it a iiif:Collection

    index_file = "manifests/index.json"
    if os.path.isfile(index_file):
        index = json.load(open(index_file))
    else:
        index = []
    index.append({
        "manifestUri": "/manifests/%s.json" % item_id
    })
    json.dump(index, open(index_file, "w"), indent=2)
    print("wrote manifests/%s.json" % item_id)

def get_thumbnail(image_info):
    w = str(image_info["sizes"][0]["width"])
    image_url = image_info["@id"].strip("/")
    return "%s/full/%s,/0/default.jpg" % (image_url, w)

def download_image(url):
    path = join('data', os.path.basename(url))
    if (os.path.isfile(path)):
        return path
    logging.info("downloading %s to %s", url, path)
    with open(path, "wb") as fh:
        resp = requests.get(url, stream=True)
        for chunk in resp.iter_content(chunk_size=1024):
            fh.write(chunk)
    return path

def get_metadata(item):
    m = {}
    for et in item.get('element_texts', []):
        key = et['element']['name'].lower()
        value = et.get('text', '')
        m[key] = value
    return m

def md5(path):
    m = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            m.update(chunk)
    return m.hexdigest()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("omeka_url", help="The Omeka instance URL")
    parser.add_argument("iiif_url", help="Where the manifest will be mounted.")
    args = parser.parse_args()
    main(args.omeka_url, args.iiif_url)
