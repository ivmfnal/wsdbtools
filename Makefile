VERSION=1.11.0
TARDIR=/tmp/$(USER)
TARFILE=$(TARDIR)/wsdbtools_$(VERSION).tar
BUILDDIR=$(HOME)/build/wsdbtools

all: clean build tarfile

build: $(BUILDDIR)
	cd wsdbtools; make VERSION=$(VERSION) BUILDDIR=$(BUILDDIR) build
	cp -R tests apps $(BUILDDIR)

tarfile: $(TARDIR)
	cd $(BUILDDIR); tar cf $(TARFILE) wsdbtools tests apps
	@echo
	@echo Tafrile is ready: $(TARFILE)
	@echo

clean:
	rm -rf $(BUILDDIR)

$(BUILDDIR):
	mkdir -p $@

$(TARDIR):
	mkdir -p $@
