/* jfix: rebuild a baseline JPEG from the surviving tail of its entropy-coded data.
 * usage: jfix tail.bin out.jpg|- [qdc]
 * tail.bin = bytes of the damaged file from the end of the encrypted area to the original end.
 * Assumes standard (Annex K) Huffman tables, 3 components, baseline sequential. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

static const uint8_t dcl_bits[16] = {0,1,5,1,1,1,1,1,1,0,0,0,0,0,0,0};
static const uint8_t dcc_bits[16] = {0,3,1,1,1,1,1,1,1,1,1,0,0,0,0,0};
static const uint8_t dc_vals[12] = {0,1,2,3,4,5,6,7,8,9,10,11};
static const uint8_t acl_bits[16] = {0,2,1,3,3,2,4,3,5,5,4,4,0,0,1,0x7d};
static const uint8_t acc_bits[16] = {0,2,1,2,4,4,3,4,7,5,4,4,0,1,2,0x77};
static const uint8_t acl_vals[162] = {
0x01,0x02,0x03,0x00,0x04,0x11,0x05,0x12,0x21,0x31,0x41,0x06,0x13,0x51,0x61,0x07,
0x22,0x71,0x14,0x32,0x81,0x91,0xa1,0x08,0x23,0x42,0xb1,0xc1,0x15,0x52,0xd1,0xf0,
0x24,0x33,0x62,0x72,0x82,0x09,0x0a,0x16,0x17,0x18,0x19,0x1a,0x25,0x26,0x27,0x28,
0x29,0x2a,0x34,0x35,0x36,0x37,0x38,0x39,0x3a,0x43,0x44,0x45,0x46,0x47,0x48,0x49,
0x4a,0x53,0x54,0x55,0x56,0x57,0x58,0x59,0x5a,0x63,0x64,0x65,0x66,0x67,0x68,0x69,
0x6a,0x73,0x74,0x75,0x76,0x77,0x78,0x79,0x7a,0x83,0x84,0x85,0x86,0x87,0x88,0x89,
0x8a,0x92,0x93,0x94,0x95,0x96,0x97,0x98,0x99,0x9a,0xa2,0xa3,0xa4,0xa5,0xa6,0xa7,
0xa8,0xa9,0xaa,0xb2,0xb3,0xb4,0xb5,0xb6,0xb7,0xb8,0xb9,0xba,0xc2,0xc3,0xc4,0xc5,
0xc6,0xc7,0xc8,0xc9,0xca,0xd2,0xd3,0xd4,0xd5,0xd6,0xd7,0xd8,0xd9,0xda,0xe1,0xe2,
0xe3,0xe4,0xe5,0xe6,0xe7,0xe8,0xe9,0xea,0xf1,0xf2,0xf3,0xf4,0xf5,0xf6,0xf7,0xf8,
0xf9,0xfa};
static const uint8_t acc_vals[162] = {
0x00,0x01,0x02,0x03,0x11,0x04,0x05,0x21,0x31,0x06,0x12,0x41,0x51,0x07,0x61,0x71,
0x13,0x22,0x32,0x81,0x08,0x14,0x42,0x91,0xa1,0xb1,0xc1,0x09,0x23,0x33,0x52,0xf0,
0x15,0x62,0x72,0xd1,0x0a,0x16,0x24,0x34,0xe1,0x25,0xf1,0x17,0x18,0x19,0x1a,0x26,
0x27,0x28,0x29,0x2a,0x35,0x36,0x37,0x38,0x39,0x3a,0x43,0x44,0x45,0x46,0x47,0x48,
0x49,0x4a,0x53,0x54,0x55,0x56,0x57,0x58,0x59,0x5a,0x63,0x64,0x65,0x66,0x67,0x68,
0x69,0x6a,0x73,0x74,0x75,0x76,0x77,0x78,0x79,0x7a,0x82,0x83,0x84,0x85,0x86,0x87,
0x88,0x89,0x8a,0x92,0x93,0x94,0x95,0x96,0x97,0x98,0x99,0x9a,0xa2,0xa3,0xa4,0xa5,
0xa6,0xa7,0xa8,0xa9,0xaa,0xb2,0xb3,0xb4,0xb5,0xb6,0xb7,0xb8,0xb9,0xba,0xc2,0xc3,
0xc4,0xc5,0xc6,0xc7,0xc8,0xc9,0xca,0xd2,0xd3,0xd4,0xd5,0xd6,0xd7,0xd8,0xd9,0xda,
0xe2,0xe3,0xe4,0xe5,0xe6,0xe7,0xe8,0xe9,0xea,0xf2,0xf3,0xf4,0xf5,0xf6,0xf7,0xf8,
0xf9,0xfa};
static const uint8_t std_lum[64] = {
16,11,10,16,24,40,51,61, 12,12,14,19,26,58,60,55, 14,13,16,24,40,57,69,56, 14,17,22,29,51,87,80,62,
18,22,37,56,68,109,103,77, 24,35,55,64,81,104,113,92, 49,64,78,87,103,121,120,101, 72,92,95,98,112,100,103,99};
static const uint8_t std_chr[64] = {
17,18,24,47,99,99,99,99, 18,21,26,66,99,99,99,99, 24,26,56,99,99,99,99,99, 47,66,99,99,99,99,99,99,
99,99,99,99,99,99,99,99, 99,99,99,99,99,99,99,99, 99,99,99,99,99,99,99,99, 99,99,99,99,99,99,99,99};
static const uint8_t zz[64] = {
0,1,8,16,9,2,3,10,17,24,32,25,18,11,4,5,12,19,26,33,40,48,41,34,27,20,13,6,7,14,21,28,
35,42,49,56,57,50,43,36,29,22,15,23,30,37,44,51,58,59,52,45,38,31,39,46,53,60,61,54,47,55,62,63};

typedef struct { uint16_t ecode[256]; uint8_t esize[256]; uint16_t *look; } HT;
static HT T[4]; /* 0 dc lum, 1 dc chr, 2 ac lum, 3 ac chr */

static void build(HT *h, const uint8_t *bits, const uint8_t *vals) {
    int code = 0, k = 0, len, i;
    h->look = (uint16_t *)calloc(65536, 2);
    memset(h->esize, 0, 256);
    for (len = 1; len <= 16; len++) {
        for (i = 0; i < bits[len - 1]; i++) {
            int sym = vals[k++];
            uint32_t base = (uint32_t)code << (16 - len), n = 1u << (16 - len), j;
            h->ecode[sym] = (uint16_t)code; h->esize[sym] = (uint8_t)len;
            for (j = 0; j < n; j++) h->look[base + j] = (uint16_t)((len << 8) | sym);
            code++;
        }
        code <<= 1;
    }
}

static uint8_t *D; static size_t NB;   /* unstuffed entropy data, number of bits */
static inline uint32_t peek16(size_t p) {
    size_t b = p >> 3; uint32_t v = ((uint32_t)D[b] << 16) | ((uint32_t)D[b + 1] << 8) | D[b + 2];
    return (v >> (8 - (p & 7))) & 0xFFFF;
}
static inline int getbits(size_t *p, int n) {
    size_t b; uint32_t v;
    if (!n) return 0;
    b = *p >> 3; v = ((uint32_t)D[b] << 24) | ((uint32_t)D[b + 1] << 16) | ((uint32_t)D[b + 2] << 8) | D[b + 3];
    v = (v << (*p & 7)) >> (32 - n); *p += n; return (int)v;
}
static inline int extend(int v, int n) { return (n && v < (1 << (n - 1))) ? v - (1 << n) + 1 : v; }

typedef struct { int16_t *blk; size_t nmcu, cap; int ny; long overflow_late, invalid_late; int endgap; int valid; int dri; } DEC;

static int dec_block(size_t *p, HT *dc, HT *ac, int16_t *o, int *bad) {
    uint16_t e; int s, k;
    memset(o, 0, 128);
    e = dc->look[peek16(*p)];
    if (!e) { (*p)++; (*bad)++; return 0; }
    *p += e >> 8; s = e & 255;
    if (s > 11) { (*bad)++; s = 11; }
    o[0] = (int16_t)extend(getbits(p, s), s);
    for (k = 1; k < 64;) {
        int r;
        e = ac->look[peek16(*p)];
        if (!e) { (*p)++; (*bad)++; return 0; }
        *p += e >> 8; r = (e & 255) >> 4; s = e & 15;
        if (!s) { if (r == 15) { k += 16; if (k > 64) { (*bad)++; return 0; } continue; } break; }
        k += r;
        if (k > 63) { (*bad)++; *p += s; return 0; }
        o[k] = (int16_t)extend(getbits(p, s), s);
        k++;
    }
    return 1;
}

/* decode MCUs from bit a to bit b; append to d. returns bits left unused */
static int dec_range(DEC *d, size_t a, size_t b, size_t lateafter) {
    int nb = d->ny + 2, i;
    size_t p = a;
    for (;;) {
        size_t save = p; int bad = 0;
        if (p + 6 * d->ny + 8 > b) break;
        if (d->nmcu + 1 > d->cap) {
            d->cap = d->cap ? d->cap * 2 : 65536;
            d->blk = (int16_t *)realloc(d->blk, d->cap * nb * 128);
            if (!d->blk) { fprintf(stderr, "oom\n"); exit(3); }
        }
        for (i = 0; i < nb; i++) {
            int c = i < d->ny ? 0 : 1;
            dec_block(&p, &T[c], &T[2 + c], d->blk + (d->nmcu * nb + i) * 64, &bad);
            if (p > b) break;
        }
        if (p > b) { p = save; break; }
        if (bad && getenv("JDBG2")) fprintf(stderr, "bad at mcu %lu bit %lu of %lu\n", (unsigned long)d->nmcu, (unsigned long)save, (unsigned long)b);
        if (bad && d->nmcu >= lateafter) d->overflow_late += bad;
        d->nmcu++;
    }
    return (int)(b - p);
}

/* ---------- output ---------- */
static FILE *fo; static uint32_t wacc; static int wn;
static void putbits(uint32_t code, int n) {
    if (!n) return;
    wacc = (wacc << n) | (code & ((1u << n) - 1)); wn += n;
    while (wn >= 8) { int c = (wacc >> (wn - 8)) & 255; fputc(c, fo); if (c == 255) fputc(0, fo); wn -= 8; }
}
static inline int cat(int v) { int n = 0; if (v < 0) v = -v; while (v) { n++; v >>= 1; } return n; }
static void enc_block(const int16_t *b, int dcdiff, int c) {
    HT *dc = &T[c], *ac = &T[2 + c]; int s, k, run = 0;
    if (dcdiff > 2047) dcdiff = 2047; if (dcdiff < -2047) dcdiff = -2047;
    s = cat(dcdiff);
    putbits(dc->ecode[s], dc->esize[s]);
    putbits((uint32_t)(dcdiff < 0 ? dcdiff - 1 : dcdiff), s);
    if (b) for (k = 1; k < 64; k++) {
        int v = b[k];
        if (!v) { run++; continue; }
        while (run > 15) { putbits(ac->ecode[0xF0], ac->esize[0xF0]); run -= 16; }
        if (v > 1023) v = 1023; if (v < -1023) v = -1023;
        s = cat(v);
        putbits(ac->ecode[(run << 4) | s], ac->esize[(run << 4) | s]);
        putbits((uint32_t)(v < 0 ? v - 1 : v), s);
        run = 0;
    }
    if (!b || run) putbits(ac->ecode[0], ac->esize[0]);
}
static void w16(int v) { fputc(v >> 8, fo); fputc(v & 255, fo); }
static int qscale(int base, int q) { int s = q < 50 ? 5000 / q : 200 - 2 * q; int v = (base * s + 50) / 100; return v < 1 ? 1 : v > 255 ? 255 : v; }
static int quality_for_qdc(int qdc) {
    int q, lo = 0, hi = 0, best = 50, bd = 999;
    for (q = 1; q <= 100; q++) {
        int v = qscale(16, q), d = abs(v - qdc);
        if (v == qdc) { if (!lo) lo = q; hi = q; }
        if (d < bd) { bd = d; best = q; }
    }
    return lo ? (lo + hi) / 2 : best;
}
static void wdht(int cls, int id, const uint8_t *bits, const uint8_t *vals, int n) {
    fputc(0xFF, fo); fputc(0xC4, fo); w16(3 + 16 + n); fputc((cls << 4) | id, fo); fwrite(bits, 1, 16, fo); fwrite(vals, 1, n, fo);
}

static int cmpf(const void *a, const void *b) { float x = *(const float *)a, y = *(const float *)b; return x < y ? -1 : x > y; }

static const int known[][2] = {
 {4128,3096},{4128,2322},{4000,3000},{5312,2988},{3264,1836},{4640,3480},{1920,1080},{4000,2250},{4032,2268},
 {4160,2340},{2592,1944},{2592,1458},{1080,1080},{1440,1080},{2160,1080},{2280,1080},{2340,1080},{3000,3000},
 {4160,3120},{3264,2448},{4608,3456},{4096,3072},{4032,3024},{3968,2976},{2048,1536},{1600,1200},{2560,1920},
 {1280,960},{640,480},{4608,2592},{3840,2160},{2560,1440},{1280,720},{4096,2304},{4208,3120},{3120,3120},
 {2448,2448},{2976,2976},{3456,3456},{4160,2080},{4608,2304},{3840,1920},{4000,2000},{5184,3888},{5184,3456},
 {6000,4000},{4000,1800},{4160,1872},{3264,1632},{4624,3468},{4624,2604},{4656,3492},{4656,2620},{3456,4608},
 {2048,1152},{3200,2400},{1632,1224},{2576,1932},{2576,1449},{3120,2340},{3120,1755},{4096,1940},{4160,1968},
 {4608,2176},{4608,2240},{4000,1848},{2304,1728},{4032,1960},{4032,1908},{3968,1984},{4208,2368},{960,720},{800,600},{1024,768}
};
#define NKNOWN (int)(sizeof(known) / sizeof(known[0]))

int main(int argc, char **argv) {
    FILE *f; long fl; uint8_t *raw; size_t i, n, nd = 0; int endmark = 0;
    size_t *rst = NULL; size_t nrst = 0, rcap = 0;
    DEC best; int cand, ny, nb, rstmode, dri = 0;
    int forceq = argc > 3 ? atoi(argv[3]) : 0;
    if (argc < 3) { fprintf(stderr, "usage\n"); return 2; }
    f = fopen(argv[1], "rb"); if (!f) { printf("status=FAIL reason=open\n"); return 1; }
    fseek(f, 0, SEEK_END); fl = ftell(f); fseek(f, 0, SEEK_SET);
    raw = (uint8_t *)malloc(fl + 16); n = fread(raw, 1, fl, f); fclose(f);
    D = (uint8_t *)malloc(n + 64);
    for (i = 0; i < n; i++) {
        uint8_t c = raw[i];
        if (c != 0xFF) { D[nd++] = c; continue; }
        if (i + 1 >= n) break;
        if (raw[i + 1] == 0) { D[nd++] = 0xFF; i++; continue; }
        if (raw[i + 1] == 0xFF) continue;
        if (raw[i + 1] >= 0xD0 && raw[i + 1] <= 0xD7) {
            if (nrst + 1 > rcap) { rcap = rcap ? rcap * 2 : 1024; rst = (size_t *)realloc(rst, rcap * sizeof(size_t)); }
            rst[nrst++] = nd; i++; continue;
        }
        endmark = raw[i + 1]; break;
    }
    memset(D + nd, 0xFF, 32);
    NB = nd * 8;
    if (endmark != 0xD9) { printf("status=FAIL reason=%s endmark=%02X scanbytes=%lu\n", endmark ? "not-baseline-or-multiscan" : "no-end-marker", endmark, (unsigned long)nd); return 1; }
    if (nd < 2000) { printf("status=FAIL reason=too-little-data scanbytes=%lu\n", (unsigned long)nd); return 1; }
    build(&T[0], dcl_bits, dc_vals); build(&T[1], dcc_bits, dc_vals); build(&T[2], acl_bits, acl_vals); build(&T[3], acc_bits, acc_vals);
    rstmode = nrst >= 2;

    memset(&best, 0, sizeof best);
    {
        static const int nys[3] = {4, 2, 1};
        for (cand = 0; cand < 3; cand++) {
            DEC d; memset(&d, 0, sizeof d); d.ny = nys[cand];
            if (!rstmode) {
                d.endgap = dec_range(&d, 0, NB, 400);
                d.valid = d.endgap < 8 && d.overflow_late == 0 && d.nmcu > 500;
            } else {
                size_t s; int ok = 1; size_t prev;
                /* learn interval from second segment */
                for (s = 0; s < nrst; s++) {
                    size_t a = rst[s] * 8, b = (s + 1 < nrst ? rst[s + 1] : nd) * 8;
                    int gap;
                    prev = d.nmcu;
                    gap = dec_range(&d, a, b, 0);
                    if (gap >= 8) ok = 0;
                    if (s == 0) dri = (int)(d.nmcu - prev);
                    else if (s + 1 < nrst && (int)(d.nmcu - prev) != dri) ok = 0;
                    if (!ok) break;
                }
                d.valid = ok && d.overflow_late == 0 && d.nmcu > 500;
                d.dri = dri;
            }
            if (getenv("JDBG")) fprintf(stderr, "cand ny=%d mcus=%lu endgap=%d bad=%ld dri=%d\n", d.ny, (unsigned long)d.nmcu, d.endgap, d.overflow_late, dri);
            if (d.valid && !best.valid) best = d; else free(d.blk);
        }
    }
    if (!best.valid) { printf("status=FAIL reason=cannot-decode(custom-huffman-or-unknown-layout) rst=%lu scanbytes=%lu\n", (unsigned long)nrst, (unsigned long)nd); return 1; }
    ny = best.ny; nb = ny + 2; dri = best.dri;
    {
        size_t M = best.nmcu, m;
        int32_t *dcabs = (int32_t *)malloc(M * nb * sizeof(int32_t));
        float *my = (float *)malloc(M * sizeof(float));
        int pred[3] = {0, 0, 0};
        int vert = 0, mw, mh, Wm = 0, Hm, W, H, R, J, j, bj = 0;
        double bests = 1e30; size_t missing;
        double sugq, rangey; int qdc, quality; int offy = 0, offb = 0, offr = 0;
        int G = rstmode ? 0 : 3;

        for (m = 0; m < M; m++) {
            int b; double s = 0;
            if (rstmode && dri && m % dri == 0) pred[0] = pred[1] = pred[2] = 0;
            for (b = 0; b < nb; b++) {
                int c = b < ny ? 0 : b - ny + 1;
                pred[c] += best.blk[(m * nb + b) * 64];
                dcabs[m * nb + b] = pred[c];
                if (b < ny) s += pred[c];
            }
            my[m] = (float)(s / ny);
        }
        /* orientation for 2 luma blocks per MCU */
        if (ny == 2) {
            double a = 0, c = 0; size_t st = M / 4;
            for (m = st; m + 1 < M; m++) { a += abs(dcabs[m * nb + 1] - dcabs[(m + 1) * nb]); c += abs(dcabs[m * nb] - dcabs[(m + 1) * nb]); }
            vert = c < a;
        }
        mw = (ny == 4 || (ny == 2 && !vert)) ? 16 : 8;
        mh = (ny == 4 || (ny == 2 && vert)) ? 16 : 8;
        /* width in MCUs: best vertical correlation */
        {
            int wmin = (int)sqrt((double)M * mh / mw / 4.2), wmax = (int)sqrt((double)M * mh / mw * 4.2) + 1, w;
            size_t st = 64, step = M > 400000 ? 3 : 1;
            if (wmin < 4) wmin = 4;
            for (w = wmin; w <= wmax && (size_t)w * 3 < M; w++) {
                double s = 0; size_t cnt = 0;
                for (m = st + w; m < M; m += step) { s += fabs(my[m] - my[m - w]); cnt++; }
                s /= cnt;
                if (s < bests) { bests = s; Wm = w; }
            }
            /* prefer a divisor if it is nearly as good (guards against picking 2x width) */
            for (w = 2; w <= 3; w++) if (Wm % w == 0 && Wm / w >= wmin) {
                double s = 0; size_t cnt = 0; int ww = Wm / w;
                for (m = st + ww; m < M; m += step) { s += fabs(my[m] - my[m - ww]); cnt++; }
                s /= cnt;
                if (s < bests * 1.15) { Wm = ww; bests = s; }
            }
        }
        R = (int)((M + Wm - 1) / Wm);
        {   /* how many rows could be missing at most */
            size_t take = (size_t)Wm * 2 < M ? (size_t)Wm * 2 : M;
            double bits_per_mcu = (double)NB / M, est;
            (void)take;
            est = 153600.0 * 8 / bits_per_mcu / Wm;
            J = (int)(est * 3) + 2;
        }
        W = Wm * mw;
        {   /* choose height: known camera size first, then common aspect ratios, else minimum */
            int found = 0, pass;
            for (j = 0; j <= J && !found; j++) {
                int k, Hp = (R + j) * mh;
                for (k = 0; k < NKNOWN && !found; k++) {
                    int a = known[k][0], b = known[k][1], o;
                    for (o = 0; o < 2; o++) {
                        int kw = o ? b : a, kh = o ? a : b;
                        if ((kw + mw - 1) / mw * mw == W && (kh + mh - 1) / mh * mh == Hp) { found = 1; bj = j; W = kw; H = kh; break; }
                    }
                }
            }
            if (!found) {
                static const double asp[] = {4.0 / 3, 3.0 / 4, 16.0 / 9, 9.0 / 16, 1.0, 3.0 / 2, 2.0 / 3, 2.0, 0.5};
                for (pass = 0; pass < 9 && !found; pass++) {
                    double bd = 0.008;
                    for (j = 0; j <= J; j++) {
                        double r = (double)W / ((R + j) * mh), dd = fabs(r / asp[pass] - 1);
                        if (dd < bd) { bd = dd; bj = j; found = 1; }
                    }
                }
                if (!found) bj = 0;
                H = (R + bj) * mh;
            }
            Hm = R + bj;
        }
        missing = (size_t)Wm * Hm - M;

        /* suggested maximum DC quantiser from luminance range */
        {
            size_t cnt = 0, st = 64; float *v = (float *)malloc(M * sizeof(float)); float lo, hi;
            for (m = st; m < M; m++) v[cnt++] = my[m];
            qsort(v, cnt, sizeof(float), cmpf);
            lo = v[(size_t)(cnt * 0.001)]; hi = v[(size_t)(cnt * 0.999)];
            rangey = hi - lo;
            if (rstmode) { double a = lo < -1 ? 1024.0 / -lo : 99, b = hi > 1 ? 1016.0 / hi : 99; sugq = a < b ? a : b; }
            else sugq = rangey > 1 ? 2040.0 / rangey : 99;
            free(v);
        }
        qdc = forceq ? forceq : (int)floor(sugq * 1.03);
        if (qdc < 1) qdc = 1; if (qdc > 40) qdc = 40;
        quality = quality_for_qdc(qdc);
        {
            int qy = qscale(16, quality), qc = qscale(17, quality);
            if (!rstmode && strcmp(argv[2], "-")) {
                /* gamut search for the unknown DC levels */
                size_t st = 64, ns = 0, step = (M - st) / 1200 + 1; float *sy, *sb, *sr; float *t;
                float medy, medb, medr; int ay, ab, ar; double bc = 1e30, accy = 0, accb = 0, accr = 0, accn = 0;
                double *cost; int gy, gb, gr, ny_, nb_, nr_; float y0, b0, r0;
                sy = (float *)malloc(3 * (M / step + 2) * sizeof(float)); sb = sy + (M / step + 2); sr = sb + (M / step + 2);
                for (m = st; m < M; m += step) {
                    sy[ns] = my[m] * qy / 8.0f; sb[ns] = dcabs[m * nb + ny] * qc / 8.0f; sr[ns] = dcabs[m * nb + ny + 1] * qc / 8.0f; ns++;
                }
                t = (float *)malloc(ns * sizeof(float));
                memcpy(t, sy, ns * sizeof(float)); qsort(t, ns, sizeof(float), cmpf); medy = t[ns / 2];
                memcpy(t, sb, ns * sizeof(float)); qsort(t, ns, sizeof(float), cmpf); medb = t[ns / 2];
                memcpy(t, sr, ns * sizeof(float)); qsort(t, ns, sizeof(float), cmpf); medr = t[ns / 2];
                free(t);
                /* grid: Y offset so that median lands in 20..235, chroma median within +-90 of neutral */
                y0 = 20 - medy; b0 = -90 - medb; r0 = -90 - medr;
                ny_ = 216 / 6 + 1; nb_ = 180 / 6 + 1; nr_ = 180 / 6 + 1;
                cost = (double *)malloc((size_t)ny_ * nb_ * nr_ * sizeof(double));
                for (gy = 0; gy < ny_; gy++) for (gb = 0; gb < nb_; gb++) for (gr = 0; gr < nr_; gr++) {
                    float oy = y0 + gy * 6, ob = b0 + gb * 6, orr = r0 + gr * 6; double c = 0; size_t k;
                    for (k = 0; k < ns; k++) {
                        float Y = sy[k] + oy, cb = sb[k] + ob, cr = sr[k] + orr;
                        float r = Y + 1.402f * cr, g = Y - 0.344f * cb - 0.714f * cr, b = Y + 1.772f * cb, e;
                        e = r < 0 ? -r : r > 255 ? r - 255 : 0; c += e * e;
                        e = g < 0 ? -g : g > 255 ? g - 255 : 0; c += e * e;
                        e = b < 0 ? -b : b > 255 ? b - 255 : 0; c += e * e;
                    }
                    cost[((size_t)gy * nb_ + gb) * nr_ + gr] = c;
                    if (c < bc) bc = c;
                }
                for (gy = 0; gy < ny_; gy++) for (gb = 0; gb < nb_; gb++) for (gr = 0; gr < nr_; gr++) {
                    double c = cost[((size_t)gy * nb_ + gb) * nr_ + gr];
                    if (c <= bc + ns * 0.5) { accy += y0 + gy * 6; accb += b0 + gb * 6; accr += r0 + gr * 6; accn++; }
                }
                ay = (int)floor(accy / accn + 0.5); ab = (int)floor(accb / accn + 0.5); ar = (int)floor(accr / accn + 0.5);
                (void)ay;
                /* pixel offsets -> DC units (pixel 128 corresponds to DC 0) */
                offy = (int)floor((accy / accn - 128) * 8.0 / qy + 0.5);
                offb = (int)floor((accb / accn) * 8.0 / qc + 0.5);
                offr = (int)floor((accr / accn) * 8.0 / qc + 0.5);
                (void)ab; (void)ar;
                free(cost); free(sy);
            }
            printf("status=OK ny=%d vert=%d rst=%lu dri=%d W=%d H=%d wm=%d hm=%d mcus=%lu missing=%lu lostpct=%.1f rangeY=%.0f sugq=%.2f qdc=%d quality=%d bpp=%.2f wscore=%.2f\n",
                   ny, vert, (unsigned long)nrst, dri, W, H, Wm, Hm, (unsigned long)M, (unsigned long)missing, 100.0 * missing / ((double)Wm * Hm),
                   rangey, sugq, qdc, quality, (double)NB / ((double)M * mw * mh), bests);
            if (strcmp(argv[2], "-")) {
                uint8_t qt[64]; int k, c; size_t total = (size_t)Wm * Hm, t2; int p[3] = {0, 0, 0};
                fo = fopen(argv[2], "wb"); if (!fo) { printf("status=FAIL reason=write\n"); return 1; }
                fputc(0xFF, fo); fputc(0xD8, fo);
                fputc(0xFF, fo); fputc(0xE0, fo); w16(16); fwrite("JFIF\0\1\1\0\0\1\0\1\0\0", 1, 14, fo);
                for (c = 0; c < 2; c++) {
                    for (k = 0; k < 64; k++) qt[k] = (uint8_t)qscale(c ? std_chr[zz[k]] : std_lum[zz[k]], quality);
                    fputc(0xFF, fo); fputc(0xDB, fo); w16(67); fputc(c, fo); fwrite(qt, 1, 64, fo);
                }
                fputc(0xFF, fo); fputc(0xC0, fo); w16(17); fputc(8, fo); w16(H); w16(W); fputc(3, fo);
                fputc(1, fo); fputc(((mw / 8) << 4) | (mh / 8), fo); fputc(0, fo);
                fputc(2, fo); fputc(0x11, fo); fputc(1, fo);
                fputc(3, fo); fputc(0x11, fo); fputc(1, fo);
                wdht(0, 0, dcl_bits, dc_vals, 12); wdht(1, 0, acl_bits, acl_vals, 162);
                wdht(0, 1, dcc_bits, dc_vals, 12); wdht(1, 1, acc_bits, acc_vals, 162);
                fputc(0xFF, fo); fputc(0xDA, fo); w16(12); fputc(3, fo);
                fputc(1, fo); fputc(0x00, fo); fputc(2, fo); fputc(0x11, fo); fputc(3, fo); fputc(0x11, fo);
                fputc(0, fo); fputc(63, fo); fputc(0, fo);
                for (t2 = 0; t2 < total; t2++) {
                    int b;
                    if (t2 < missing + G) {
                        for (b = 0; b < nb; b++) { int cc = b < ny ? 0 : b - ny + 1; enc_block(NULL, 0 - p[cc], cc > 0); p[cc] = 0; }
                    } else {
                        m = t2 - missing;
                        for (b = 0; b < nb; b++) {
                            int cc = b < ny ? 0 : b - ny + 1;
                            int v = dcabs[m * nb + b] + (cc == 0 ? offy : cc == 1 ? offb : offr);
                            int lim = 1024 * 8 / (cc ? qc : qy) / 8 + 8;
                            if (lim > 2040) lim = 2040;
                            if (v > lim) v = lim; if (v < -lim) v = -lim;
                            enc_block(best.blk + (m * nb + b) * 64, v - p[cc], cc > 0); p[cc] = v;
                        }
                    }
                }
                if (wn) putbits(0x7F, 8 - wn);
                fputc(0xFF, fo); fputc(0xD9, fo); fclose(fo);
            }
        }
    }
    return 0;
}
