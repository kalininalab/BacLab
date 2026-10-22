# BacLab

**BacLab** (the BacLab code base) is a self-hosted, containerized web platform that lets a research group run bacterial genomics and genome-mining tools on its
own, unpublished data - quickly and securely, on its own hardware, without a command line. It bundles 35 tools (quality control and assembly, resistance and
plasmid screening, typing and taxonomy, comparative genomics, annotation and biosynthetic gene cluster analysis, sequence search) behind one interface.

* **Try it without installing anything:** the [demonstrations](demos.md) show the real pages and results in your browser.
* **One command** installs, updates, backs up and checks it (`./baclab install | update | db install | selftest`); an update never touches users, jobs or databases.
* **Tools are folders**: add one by copying a scaffold, or define one in the browser as an administrator.
* **Several users**: optional accounts, groups, private runs, projects, API keys, job limits and a live monitor.

```{toctree}
:maxdepth: 1
:caption: Using BacLab

demos
getting-started
ADMIN_GUIDE
```

```{toctree}
:maxdepth: 1
:caption: Reference

tools
databases
```

```{toctree}
:maxdepth: 1
:caption: Project

development
changelog
citing
```
