# Third-party components

Deadbolt's own source is Apache-2.0. Dependency components retain their original
licenses. Native archives include `THIRD-PARTY-NOTICES.txt`, generated from the
locked runtime/build dependency closure, including components conditional on
other supported targets. This inventory is broader than the exact linked set on
one platform.

`option-ext` 0.2.0 is licensed under MPL-2.0. Its unmodified source and original
license are included in `third-party/option-ext-0.2.0/`, available under that
license. The source is also available in the
[exact upstream crate](https://crates.io/crates/option-ext/0.2.0). This directory
is a source distribution for recipients, not a patched/vendored Cargo dependency.
See [Mozilla's distribution FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).

Release binaries use Rust 1.85; its runtime license and copyright notices are
included in `third-party/rust-1.85.0/`, copied from that toolchain distribution.
Windows archives request static C-runtime linkage; Windows OS components retain
their own terms. The archive does not redistribute Windows system DLLs.

Regenerate the dependency inventory with Python 3.11+ from a locked source
checkout after resolving its Cargo dependencies:

```sh
python3 dist/collect_licenses.py THIRD-PARTY-NOTICES.txt
```

The native packager does this automatically. If a dependency changes, review
its declared license and notices and update any required source distribution
before publishing. Third-party license texts do not change Deadbolt's own license
or grant rights to proprietary Harness code.
