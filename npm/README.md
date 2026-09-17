# @diphylleia/emoji

Noto Color Emoji built from source for the web, as one family, `Diphylleia
Emoji`, in two colour formats. Each browser downloads only the one it renders:

- `DiphylleiaEmoji-COLRv1.woff2` for Chromium and Firefox.
- `DiphylleiaEmoji-sbix.woff2` for Safari, which renders COLRv1 incorrectly
  and (as of iOS 18.7) draws nothing for OT-SVG in page text.

Both carry the cmap and GSUB changes WebKit needs to pick this font for
`base + U+FE0F` sequences when a text font precedes it in the font stack.

## Use

```sh
npm install @diphylleia/emoji
```

```js
import "@diphylleia/emoji";                              // diphylleia-emoji.css
import "@diphylleia/emoji/diphylleia-emoji-noflags.css"; // leaves region flags to the system, ~700 KB smaller
```

```css
:root { font-family: "Diphylleia", "Diphylleia Emoji", sans-serif; }
```

Or from a CDN:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@diphylleia/emoji@0.1.0/diphylleia-emoji.css">
```

The stylesheet's `unicode-range` makes browsers fetch the font only when a
page contains emoji.

## Source and licence

Built in [Cierra-Runis/Diphylleia-Emoji](https://github.com/Cierra-Runis/Diphylleia-Emoji),
a fork of [Noto Emoji](https://github.com/googlefonts/noto-emoji). The fonts
are under the [SIL Open Font License 1.1](LICENSE).
