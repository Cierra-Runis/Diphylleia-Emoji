"""Turn the built fonts into Diphylleia Emoji web fonts.

Reads the CBDT and COLRv1 fonts from 2D/fonts (the output of the pipeline in
full_rebuild.sh) and writes WOFF2 files for the web:

- DiphylleiaEmoji-COLRv1.woff2: Noto-COLRv1.ttf, subset and renamed. For
  Chromium and Firefox.
- DiphylleiaEmoji-sbix.woff2: the PNG strike of NotoColorEmoji.ttf moved into
  an sbix table, plus the empty glyf table CoreText expects. For Safari, which
  renders COLRv1 as solid blocks (Safari 27) and, as of iOS 18.7, draws
  nothing for OT-SVG in page text.

Both also get the fixes WebKit needs to pick this font for "base + U+FE0F"
sequences when a text font precedes it in the font stack; see
map_variation_selector().

    python web_fonts.py            # with region flags, into npm/dist
    python web_fonts.py --noflags  # without region flags
"""

import io
import shutil
from argparse import ArgumentParser
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.tables.otBase import BaseTable
from fontTools.ttLib.tables.sbixGlyph import Glyph as SbixGlyph
from fontTools.ttLib.tables.sbixStrike import Strike

ROOT = Path(__file__).resolve().parent
FONTS = ROOT / "2D" / "fonts"
FAMILY = "Diphylleia Emoji"
LICENSE = "LICENSE-DiphylleiaEmoji.txt"
PROJECT_URL = "https://github.com/Cierra-Runis/Diphylleia-Emoji"
VENDOR_ID = "DPHY"


def cbdt_to_sbix(font):
    """Move the CBDT PNG strike into an sbix table and drop CBDT/CBLC."""
    strike_size = font["CBLC"].strikes[0].bitmapSizeTable
    strike = Strike(ppem=strike_size.ppemY, resolution=72)
    for name, bitmap in font["CBDT"].strikeData[0].items():
        metrics = bitmap.metrics
        strike.glyphs[name] = SbixGlyph(
            glyphName=name,
            graphicType="png ",
            imageData=bitmap.imageData,
            originOffsetX=metrics.BearingX,
            # CBDT measures to the top edge, sbix to the bottom edge.
            originOffsetY=metrics.BearingY - metrics.height,
        )
    sbix = newTable("sbix")
    sbix.strikes = {strike.ppem: strike}
    font["sbix"] = sbix
    del font["CBDT"]
    del font["CBLC"]


def add_empty_glyf(font):
    """The CBDT font has no outlines at all; CoreText wants a glyf table."""
    order = font.getGlyphOrder()
    glyf = newTable("glyf")
    glyf.glyphs = {name: Glyph() for name in order}
    glyf.glyphOrder = order
    font["glyf"] = glyf
    font["loca"] = newTable("loca")
    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    for field in (
        "maxPoints",
        "maxContours",
        "maxCompositePoints",
        "maxCompositeContours",
        "maxZones",
        "maxTwilightPoints",
        "maxStorage",
        "maxFunctionDefs",
        "maxInstructionDefs",
        "maxStackElements",
        "maxSizeOfInstructions",
        "maxComponentElements",
        "maxComponentDepth",
    ):
        setattr(maxp, field, 0)
    maxp.maxZones = 1


def drop_text_codepoints(font):
    """Unmap the space and control characters the font carries for Android.

    Their glyphs are as wide as an emoji, so a page whose font stack reaches
    this font for U+0020 gets emoji-sized spaces.
    """
    for table in font["cmap"].tables:
        if table.format != 14:
            for codepoint in (0x0000, 0x000D, 0x0020):
                table.cmap.pop(codepoint, None)


def map_variation_selector(font):
    """Make WebKit believe this font handles U+FE0F on its own.

    WebKit's CoreText backend decides which font renders "base + FE0F" by
    asking each font for FE0F as a standalone character (WebKit bug 258877).
    Two things make this font answer "no": FE0F has no plain cmap mapping,
    and while a cmap format 14 subtable lists FE0F as a variation selector
    CoreText refuses to return a glyph for it even when one is mapped. So
    FE0F gets an empty zero-width glyph, and the format 14 subtable goes: its
    entries are all default UVS records, i.e. "use the base glyph", which is
    what the plain cmap already does. drop_variation_selector_glyph() then
    keeps the new glyph out of the shaper's way.
    """
    name = "uniFE0F"
    font.setGlyphOrder(font.getGlyphOrder() + [name])
    font["glyf"][name] = Glyph()
    font["hmtx"][name] = (0, 0)
    if "vmtx" in font:
        font["vmtx"][name] = (0, 0)
    cmap = font["cmap"]
    cmap.tables = [table for table in cmap.tables if table.format != 14]
    for table in cmap.tables:
        table.cmap[0xFE0F] = name


def _shift_lookup_indices(obj):
    """Renumber every lookup reference after a lookup is inserted at index 0."""
    if isinstance(obj, list):
        for item in obj:
            _shift_lookup_indices(item)
    elif isinstance(obj, dict):
        for item in obj.values():
            _shift_lookup_indices(item)
    elif isinstance(obj, otTables.SubstLookupRecord):
        obj.LookupListIndex += 1
    elif isinstance(obj, otTables.Feature):
        obj.LookupListIndex = [index + 1 for index in obj.LookupListIndex]
    elif isinstance(obj, BaseTable):
        for item in vars(obj).values():
            _shift_lookup_indices(item)


def drop_variation_selector_glyph(font):
    """Delete the U+FE0F glyph during shaping, before any ligature forms.

    With FE0F mapped in cmap, CoreText puts its glyph into the glyph stream
    and "1 FE0F 20E3" no longer matches the keycap ligature. A deletion in
    the first lookup restores the stream shapers saw when FE0F was unmapped.
    """
    scratch = TTFont()
    scratch.setGlyphOrder(font.getGlyphOrder())
    addOpenTypeFeaturesFromString(
        scratch,
        "languagesystem DFLT dflt;\n"
        "lookup drop_vs { sub uniFE0F by NULL; } drop_vs;\n"
        "feature ccmp { lookup drop_vs; } ccmp;\n",
    )
    gsub = font["GSUB"].table
    _shift_lookup_indices(gsub.LookupList)
    _shift_lookup_indices(gsub.FeatureList)
    gsub.LookupList.Lookup.insert(0, scratch["GSUB"].table.LookupList.Lookup[0])
    gsub.LookupList.LookupCount += 1
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag == "ccmp":
            record.Feature.LookupListIndex.insert(0, 0)
            record.Feature.LookupCount += 1


def rename(font, description):
    """Give the font its own name, as the OFL asks of a modified version.

    Google's copyright and the licence records stay; the Noto trademark
    notice goes, since the name no longer uses it.
    """
    name = font["name"]
    # Upstream: "Version 2.051;GOOG;noto-emoji:20250818:<commit>". Keep the
    # number and the upstream build tag so the source revision stays visible.
    version, _, upstream = name.getDebugName(5).removeprefix("Version ").split(";")
    records = {
        0: f"{name.getDebugName(0)} Modified for Diphylleia ({PROJECT_URL}).",
        1: FAMILY,
        3: f"{FAMILY} Regular;{version};{VENDOR_ID}",
        4: FAMILY,
        5: f"Version {version};{VENDOR_ID};{upstream}",
        6: FAMILY.replace(" ", "") + "-Regular",
        10: description,
        11: PROJECT_URL,
    }
    name.removeNames(nameID=7)
    for name_id, value in records.items():
        name.setName(value, name_id, 3, 1, 0x409)
    font["OS/2"].achVendID = VENDOR_ID


def codepoints(font):
    return {
        codepoint
        for table in font["cmap"].tables
        if table.isUnicode()
        for codepoint in table.cmap
    }


def unicode_range(codepoints):
    ranges = []
    for codepoint in sorted(codepoints):
        if ranges and codepoint == ranges[-1][1] + 1:
            ranges[-1][1] = codepoint
        else:
            ranges.append([codepoint, codepoint])
    return ", ".join(
        f"U+{start:X}" if start == end else f"U+{start:X}-{end:X}"
        for start, end in ranges
    )


def stylesheet(colr, sbix, suffix):
    """The @font-face users link. Committed next to this script; CI checks it."""
    # tech() lets each browser download only the colour format it renders:
    # COLRv1 for Chromium and Firefox, sbix for Safari. Browsers without
    # tech() skip the whole src list and fall back to the system emoji.
    return f"""@font-face {{
  font-family: "{FAMILY}";
  font-display: swap;
  src:
    url("./dist/DiphylleiaEmoji-COLRv1{suffix}.woff2") format("woff2") tech(color-COLRv1),
    url("./dist/DiphylleiaEmoji-sbix{suffix}.woff2") format("woff2") tech(color-sbix);
  unicode-range: {unicode_range(codepoints(colr) | codepoints(sbix))};
}}
"""


def subset_for_web(font):
    """Drop glyphs nothing reaches any more and strip glyph names."""
    options = Options()
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.name_legacy = True
    options.layout_features = ["*"]
    options.notdef_outline = True
    options.glyph_names = False
    subsetter = Subsetter(options)
    subsetter.populate(unicodes=codepoints(font))
    subsetter.subset(font)


def save_woff2(font, path):
    """Write WOFF2 next to the licence every build must ship with."""
    shutil.copyfile(FONTS / "LICENSE", path.parent / LICENSE)
    font.flavor = "woff2"
    buffer = io.BytesIO()
    font.save(buffer)
    path.write_bytes(buffer.getvalue())
    print(
        f"{path}: {len(buffer.getvalue()) / 1024:.0f} KB, {len(font.getGlyphOrder())} glyphs"
    )


def main():
    parser = ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--noflags", action="store_true", help="Use the fonts without region flags."
    )
    parser.add_argument("--out", type=Path, default=ROOT / "npm" / "dist")
    args = parser.parse_args()

    suffix = "-noflags" if args.noflags else ""
    args.out.mkdir(parents=True, exist_ok=True)

    colr = TTFont(FONTS / f"Noto-COLRv1{suffix}.ttf")
    drop_text_codepoints(colr)
    map_variation_selector(colr)
    drop_variation_selector_glyph(colr)
    subset_for_web(colr)
    rename(
        colr, "Colour emoji font using COLRv1 glyph data, built from Noto Color Emoji."
    )
    save_woff2(colr, args.out / f"DiphylleiaEmoji-COLRv1{suffix}.woff2")

    sbix = TTFont(FONTS / f"NotoColorEmoji{suffix}.ttf")
    drop_text_codepoints(sbix)
    cbdt_to_sbix(sbix)
    add_empty_glyf(sbix)
    map_variation_selector(sbix)
    drop_variation_selector_glyph(sbix)
    rename(
        sbix, "Colour emoji font using sbix glyph data, built from Noto Color Emoji."
    )
    save_woff2(sbix, args.out / f"DiphylleiaEmoji-sbix{suffix}.woff2")

    css = ROOT / "npm" / f"diphylleia-emoji{suffix}.css"
    css.write_text(stylesheet(colr, sbix, suffix), encoding="utf-8")
    print(css)


if __name__ == "__main__":
    main()
