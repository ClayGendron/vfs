#include <cstdio>
#include <stdexcept>
int f(int x) { if (x > 1) throw std::runtime_error("boom"); return x; }
int main() { try { printf("f(1)=%d\n", f(1)); printf("f(2)=%d\n", f(2)); } catch (std::exception &e) { printf("caught %s\n", e.what()); } return 0; }
