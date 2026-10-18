"""Download pinned public sources only, never models or private user files."""

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    (
        "openblas-libs-f76e4c29.tar.gz",
        "https://codeload.github.com/MacPython/openblas-libs/tar.gz/f76e4c29cd7983c6f8ae2e41e8bdd5669dda60d8",
        "b7a0700386b4d33728d69b98b33ff632213af14348cab20ef17d7de4439ed65a",
    ),
    (
        "zlib-v1.2.13.tar.gz",
        "https://zlib.net/fossils/zlib-1.2.13.tar.gz",
        "b3a24de97a8fdbc835b9833169501030b8977031bcb54b3b3ac13740f846ab30",
    ),
    (
        "tensorflow-fad6b3cf.tar.gz",
        "https://codeload.github.com/tensorflow/tensorflow/tar.gz/fad6b3cf5a7d51a437bd01ee929853bc8554b618",
        "2b5028c480ea8029701056f8ddb80ce12ba31c9cf402183107cbb34d2db899e8",
    ),
    (
        "eigen-4c38131a.tar.gz",
        "https://gitlab.com/libeigen/eigen/-/archive/4c38131a16803130b66266a912029504f2cf23cd/eigen-4c38131a16803130b66266a912029504f2cf23cd.tar.gz",
        "1a432ccbd597ea7b9faa1557b1752328d6adc1a3db8969f6fe793ff704be3bf0",
    ),
    (
        "XNNPACK-68167d1f.zip",
        "https://codeload.github.com/google/XNNPACK/zip/68167d1fefa50296f0588ec280f48c58357ca898",
        "7235b2b55fbf11b64f38db130efae0f293d2d6d6fd90613221b598a8847f41c5",
    ),
    (
        "cpuinfo-8a921006.zip",
        "https://codeload.github.com/pytorch/cpuinfo/zip/8a9210069b5a37dd89ed118a783945502a30a4ae",
        "c0254ce97f7abc778dd2df0aaca1e0506dba1cd514fdb9fe88c07849393f8ef4",
    ),
    (
        "pthreadpool-99522991.zip",
        "https://codeload.github.com/google/pthreadpool/zip/995229919303dd98c0f1b3b585b54527067ef893",
        "d5a78b017839ee0474e6aef6e21742b03f641b260f29faf9538a0a6b8fae0704",
    ),
    (
        "ruy-3286a34c.zip",
        "https://codeload.github.com/google/ruy/zip/3286a34cc8de6149ac6844107dfdffac91531e72",
        "a22c42e80c7bb450db8492728e4742ee66f46d5458c45fe67ce2c9b61240630c",
    ),
    (
        "gemmlowp-16e8662c.zip",
        "https://codeload.github.com/google/gemmlowp/zip/16e8662c34917be0065110bfcd9cc27d30f52fdf",
        "7dc418717c8456473fac4ff2288b71057e3dcb72894524c734a4362cdb51fa8b",
    ),
    (
        "abseil-9687a8ea.tar.gz",
        "https://codeload.github.com/abseil/abseil-cpp/tar.gz/9687a8ea750bfcddf790372093245a1d041b21a3",
        "f841f78243f179326f2a80b719f2887c38fe226d288ecdc46e2aa091e6aa43bc",
    ),
    (
        "re2-03da4fc0.tar.gz",
        "https://codeload.github.com/google/re2/tar.gz/03da4fc0857c285e3a26782f6bc8931c4c950df4",
        "ef516fb84824a597c4d5d0d6d330daedb18363b5a99eda87d027e6bdd9cba299",
    ),
    (
        "sentencepiece-v0.1.96.zip",
        "https://codeload.github.com/google/sentencepiece/zip/refs/tags/v0.1.96",
        "8409b0126ebd62b256c685d5757150cf7fcb2b92a2f2b98efb3f38fc36719754",
    ),
    (
        "protobuf-v5.28.3.zip",
        "https://codeload.github.com/protocolbuffers/protobuf/zip/refs/tags/v5.28.3",
        "f645e6e42745ce922ca5388b1883ca583bafe4366cc74cf35c3c9299005136e2",
    ),
    (
        "flatbuffers-595bf000.tar.gz",
        "https://codeload.github.com/google/flatbuffers/tar.gz/595bf0007ab1929570c7671f091313c8fc20644e",
        "987300083ec1f1b095d5596ef8fb657ba46c45d786bc866a5e9029d7590a5e48",
    ),
    (
        "gcc-10.3.0.tar.xz",
        "https://ftp.gnu.org/gnu/gcc/gcc-10.3.0/gcc-10.3.0.tar.xz",
        "64f404c1a650f27fc33da242e1f2df54952e3963a49e06e73f6940f3223ac344",
    ),
    (
        "numpy-v1.26.4.tar.gz",
        "https://codeload.github.com/numpy/numpy/tar.gz/refs/tags/v1.26.4",
        "d8aec44c320c1753e60590a19d6510aacdd940586b9697b31dfb2875223c795d",
    ),
    (
        "OpenBLAS-c2f4bdbb.tar.gz",
        "https://codeload.github.com/OpenMathLib/OpenBLAS/tar.gz/c2f4bdbb",
        "39733784bdbe90d2634d94e276a5180577ebc1c69447aaed8191d865edb616a7",
    ),
    (
        "mediapipe-v0.10.32.tar.gz",
        "https://codeload.github.com/google-ai-edge/mediapipe/tar.gz/refs/tags/v0.10.32",
        "fa4272055992cc2d42d615a6ed2870f5607067bcdde9eea20bba569bc1e5454e",
    ),
    (
        "tokenizers-v0.23.3.tar.gz",
        "https://codeload.github.com/huggingface/tokenizers/tar.gz/refs/tags/v0.23.3",
        "2a0ff80c61f263cca608264a99b43dd487a3194a362d20c31193bc083e16a46b",
    ),
    (
        "ctranslate2-v4.8.3.tar.gz",
        "https://codeload.github.com/OpenNMT/CTranslate2/tar.gz/refs/tags/v4.8.3",
        "255009e3f25808e67d4c3500fd69e74076d814a62784eaf544b39fc5a472bcd9",
    ),
    (
        "onednn-v3.1.1.tar.gz",
        "https://codeload.github.com/oneapi-src/oneDNN/tar.gz/refs/tags/v3.1.1",
        "d1cd58f57b2308d362a9bc474acbc21524cb879cf5d8779b460c718f0fac82d6",
    ),
    (
        "av-17.1.0.tar.gz",
        "https://files.pythonhosted.org/packages/5e/e3/477fa20578c284abeda08d91b63ee9abaebc93445d8feeb989d3d444bae1/av-17.1.0.tar.gz",
        "7f1e71ff621b66253333926f948e00faae11d855b2442133c65128bca64cdeb3",
    ),
    (
        "qtbase-v6.8.3.tar.gz",
        "https://codeload.github.com/qt/qtbase/tar.gz/refs/tags/v6.8.3",
        "cea5c8f2c20d9cbd684f8a402721e63b87a2886e906f6ec7e0f7e1ff69c83206",
    ),
    (
        "qtsvg-v6.8.3.tar.gz",
        "https://codeload.github.com/qt/qtsvg/tar.gz/refs/tags/v6.8.3",
        "fb53da582e98d23cbf6e8bedb71efb60720e61a982d31a741742c543e2f3838d",
    ),
    (
        "pyside-setup-v6.8.3.tar.gz",
        "https://codeload.github.com/pyside/pyside-setup/tar.gz/refs/tags/v6.8.3",
        "055b467903327e947b60ddefd2e9e66f6b7558b92a0728c4596e0dc8ce5dd695",
    ),
    (
        "qtimageformats-v6.8.3.tar.gz",
        "https://codeload.github.com/qt/qtimageformats/tar.gz/refs/tags/v6.8.3",
        "ad5039af9382395641e68905e26d5e29c6fd4e02a93214c8c9df3ef88c16a26f",
    ),
    (
        "qttranslations-v6.8.3.tar.gz",
        "https://codeload.github.com/qt/qttranslations/tar.gz/refs/tags/v6.8.3",
        "8f1c2d7450864fee88c1aec86fe196d683397c15381ca02e9a94911a418ec9d9",
    ),
    (
        "ffmpeg-e4c7fbf6c0.tar.gz",
        "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/e4c7fbf6c0",
        "ce795707ff1c22e46f5c45ee330990b9fc19924e6f34bd547c73f297df80eb3c",
    ),
]


def main():
    folder = ROOT / "dist/LicenseSources"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, url, digest in SOURCES:
        path = folder / name
        if not path.exists():
            urllib.request.urlretrieve(url, path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Source archive hash mismatch: " + name)
        manifest.append({"name": name, "url": url, "sha256": digest})
    (folder / "SOURCES.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    print("PINNED_LICENSE_SOURCES_OK")


if __name__ == "__main__":
    main()
