/*
 * INQUIRE (..., EXIST= / OPENED= / NAMED= / PENDING=) for the WebAssembly build of AERMOD.
 *
 * The Flang Fortran runtime declares
 *
 *     bool _FortranAioInquireLogical(Cookie, std::uint64_t keywordHash, bool &);
 *
 * but r-wasm's Flang, compiling for wasm32, lowers calls to it with a 32-bit
 * keyword hash. wasm-ld then links each such call to a stub that traps
 * ("RuntimeError: unreachable"), and AERMOD dies at its first INQUIRE.
 *
 * scripts/build_aermod_wasm.sh renames those calls, in the compiled LLVM IR,
 * to pyaermod_FortranAioInquireLogical32 below, which takes the hash as the
 * 32 bits it was given, recovers the 64-bit hash of the keyword it stands for
 * and calls the runtime with the right signature. The hashes of EXIST, NAMED
 * and OPENED fit in 32 bits; PENDING's does not, but its low 32 bits still
 * differ from the others'.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

bool _FortranAioInquireLogical(void *cookie, uint64_t inquiry, bool *result);

/* Fortran::runtime::io::HashInquiryKeyword, for upper-case keywords. */
static uint64_t hash_keyword(const char *p) {
  uint64_t hash = 1;
  for (; *p; ++p) {
    hash = 26 * hash + (uint64_t)(*p - 'A');
  }
  return hash;
}

static const char *const logical_keywords[] = {"EXIST", "NAMED", "OPENED", "PENDING"};

bool pyaermod_FortranAioInquireLogical32(void *cookie, uint32_t truncated, bool *result) {
  for (size_t i = 0; i < sizeof logical_keywords / sizeof logical_keywords[0]; ++i) {
    uint64_t hash = hash_keyword(logical_keywords[i]);
    if ((uint32_t)hash == truncated) {
      return _FortranAioInquireLogical(cookie, hash, result);
    }
  }
  fprintf(stderr, "aermod-wasm: INQUIRE keyword with hash %u is not one of EXIST, NAMED, "
                  "OPENED, PENDING\n", (unsigned)truncated);
  abort();
}
