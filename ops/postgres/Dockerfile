# PostgreSQL 16 on Alpine with pgvector (plan 15-6). The live data directory was initialised
# by postgres:16-alpine (musl, en_US.utf8): staying on the same base keeps text sort order, and
# with it every text index, unchanged. The official pgvector images are Debian (glibc), whose
# collation differs and would need a reindex.
FROM postgres:16-alpine

ARG PGVECTOR_VERSION=0.8.7
# with_llvm=no: no JIT bitcode (the base image's LLVM toolchain is not installed)
RUN apk add --no-cache --virtual .pgvector-build git build-base \
    && git clone --depth 1 --branch "v${PGVECTOR_VERSION}" https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector OPTFLAGS="" with_llvm=no \
    && make -C /tmp/pgvector OPTFLAGS="" with_llvm=no install \
    && rm -rf /tmp/pgvector \
    && apk del .pgvector-build
