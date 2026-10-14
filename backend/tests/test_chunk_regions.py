"""regions_of() over Docling provenance faked with SimpleNamespace."""
from types import SimpleNamespace

from docling_core.types.doc.base import BoundingBox, CoordOrigin

from app.ingest.convert import regions_of


def item(*provs):
    return SimpleNamespace(prov=list(provs))


def prov(page_no: int, l: float, t: float, r: float, b: float, origin=CoordOrigin.BOTTOMLEFT):
    return SimpleNamespace(page_no=page_no, bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=origin))


def page(width: float, height: float):
    return SimpleNamespace(size=SimpleNamespace(width=width, height=height))


def test_a_bottom_left_box_becomes_top_left_with_the_page_size_attached():
    # Bottom-left origin, page height 792: a box whose top edge sits 50pt below the top of the page
    regions = regions_of([item(prov(1, l=10, t=742, r=110, b=700))], {1: page(612, 792)})

    assert regions == [{"page": 1, "l": 10, "t": 50, "r": 110, "b": 92, "page_width": 612, "page_height": 792}]


def test_top_and_bottom_are_normalised_so_top_never_exceeds_bottom():
    # to_top_left_origin does not guarantee t <= b
    regions = regions_of([item(prov(1, l=0, t=20, r=10, b=70))], {1: page(100, 100)})

    [region] = regions
    assert region["t"] < region["b"]


def test_an_item_spanning_two_pages_yields_one_region_per_page_with_its_own_size():
    regions = regions_of(
        [item(prov(1, l=0, t=0, r=10, b=10), prov(2, l=0, t=0, r=10, b=10))],
        {1: page(600, 800), 2: page(400, 500)},
    )

    assert [r["page"] for r in regions] == [1, 2]
    assert [r["page_width"] for r in regions] == [600, 400]


def test_a_page_number_missing_from_the_document_is_skipped_not_a_crash():
    regions = regions_of([item(prov(9, l=0, t=0, r=1, b=1))], {1: page(600, 800)})

    assert regions == []


def test_an_item_with_no_provenance_yields_no_regions():
    # docling's msword backend sets no prov at all -- this is the DOCX shape
    assert regions_of([item()], {1: page(600, 800)}) == []


def test_several_items_are_flattened_into_one_list_in_order():
    regions = regions_of(
        [item(prov(1, l=0, t=0, r=1, b=1)), item(prov(1, l=2, t=2, r=3, b=3))],
        {1: page(600, 800)},
    )

    assert [r["l"] for r in regions] == [0, 2]
