LIBDIR = $(BUILDDIR)/wsdbtools
LIBFILES = __init__.py dbdig.py ConnectionPool.py transaction.py rfc2617.py wda.py

all:
	@ echo This makefile must be invoked from the parent makefile

build: $(LIBDIR) $(APPSDIR)
	cp $(LIBFILES) $(LIBDIR)

$(LIBDIR):
	mkdir -p $@

$(APPSDIR):
	mkdir -p $@
