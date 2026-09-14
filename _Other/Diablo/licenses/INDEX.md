# Dependency notices

These files preserve located notice texts byte-for-byte. They do not grant
additional rights or establish that every distribution condition is satisfied.
Asset/font notices, remaining nested-component coverage, source/relinking
requirements and distribution-composition review remain qualification work.

The dependency sources came from the `diablo-arm-engine-transport` build cache.
Its executable SHA-256 is
`f444ce3fce534b43c1157540adf1a40fd596e7de43382b2d1619baa71ee77c6d`, matching
the packaged ARM runtime. Paths in the table are relative to that build's
`_deps` directory. The package manifest records the copied files' exact hashes.

| Packaged file | Source |
| --- | --- |
| sdl2.txt | sdl2-src/LICENSE.txt |
| asio.txt | asio-src/asio/LICENSE_1_0.txt |
| asio-COPYING.txt | asio-src/asio/COPYING |
| libsodium.txt | libsodium-src/LICENSE |
| libzt.txt | libzt-src/LICENSE.txt |
| libsmackerdec.txt | libsmackerdec-src/COPYING |
| sdl-audiolib-GPL.txt | sdl_audiolib-src/COPYING |
| sdl-audiolib-LGPL.txt | sdl_audiolib-src/COPYING.LESSER |
| speex-resampler.txt | sdl_audiolib-src/3rdparty/speex_resampler/resample.c, complete opening copyright/license comment |
| dr-libs.txt | sdl_audiolib-src/3rdparty/dr_libs/dr_mp3.h and dr_wav.h, MIT No Attribution alternative; dr_mp3.h minimp3 notice |
| mpqfs.txt | mpqfs-src/LICENSE |
| bzip2.txt | bzip2-src/LICENSE |
| sheenbidi.txt | sheenbidi-src/LICENSE |
| sdl-image.txt | sdl_image-src/COPYING.txt |
| libpng.txt | libpng-src/LICENSE |
| zlib.txt | zlib-src/LICENSE |
| magic-enum.txt | magic_enum-src/LICENSE |
| unordered-dense.txt | unordered_dense-src/LICENSE |
| sol2.txt | sol2-src/LICENSE.txt |
| fmt.txt | sdl_audiolib-src/3rdparty/fmt/LICENSE.rst |
| concurrentqueue.txt | libzt-src/ext/concurrentqueue/LICENSE.md |
| zerotier-license.txt | libzt-src/ext/ZeroTierOne/LICENSE.txt |
| zerotier-copying.txt | libzt-src/ext/ZeroTierOne/COPYING |
| lwip.txt | libzt-src/ext/lwip/COPYING |
| libnatpmp.txt | libzt-src/ext/ZeroTierOne/ext/libnatpmp/LICENSE |
| miniupnpc.txt | libzt-src/ext/ZeroTierOne/ext/miniupnpc/LICENSE |
| lua-readme.html | lua-src/lua-5.4.7/doc/readme.html; includes the complete Lua license section |

The remaining files came from the matching `diablo-toolchain-1.3.1`
cross-toolchain's `share/licenses/gcc` directory. The saved CMake compiler
record identifies GCC 15.2.0. `gcc-GPL3.txt` preserves `COPYING3`,
`gcc-runtime-exception.txt` preserves `COPYING.RUNTIME`, and
`libstdc-pstl.txt` preserves `libstdc++-v3/include/pstl/LICENSE.txt`.
The latter is retained conservatively; its presence does not assert that
parallel STL code was instantiated in the executable.

`assets-CC-BY.txt` and `assets-OFL.txt` are exact copies of
`Packaging/resources/LICENSE.CC-BY.txt` and `LICENSE.OFL.txt` from pinned
DevilutionX commit `0ff3186238e7c2786c4d52c21ecce1cb83723ed9`.
Its `Packaging/nix/LinuxReleasePackaging.sh` includes both in Linux releases;
`Source/DiabloUI/support_lines.cpp` identifies Charis SIL, New Athena Unicode,
Unifont, Noto, and Twitmoji as font/emoji components. Our runtime assets
include converted `fonts/*.clx` files. These preserved texts are not a
per-file ownership determination: remaining asset attribution, modifications,
and distribution obligations must still be checked before release.
