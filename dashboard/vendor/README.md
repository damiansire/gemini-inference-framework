# vendor/

`chart.umd.min.js` is [Chart.js](https://www.chartjs.org/) v4.4.7 (MIT
license), vendored instead of loaded from a CDN.

Fetched from `https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js`
on 2026-07-10. jsDelivr's own comment in the file notes it should not be
pinned with SRI (it's a dynamically assembled combined build), so vendoring
is the actual fix, not a workaround: this page is deployed publicly
(GitHub Pages) and previously loaded unauthenticated third-party JS with no
integrity check at all.

To bump the version: download the new `chart.umd.min.js` from
`https://cdn.jsdelivr.net/npm/chart.js@<version>/dist/chart.umd.min.js` and
replace this file.
