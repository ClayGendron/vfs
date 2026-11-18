# Rendering

A file that is not text, such as a PDF or a spreadsheet, is rendered to text so that it can be read and searched. The `rendering` module holds the renderers, the registry that picks one by file type, and the limits a render runs inside.

```python
from vfs import rendering
```

`DatabaseStorage` takes a `rendering.RendererRegistry` as `renderers` and a `rendering.RenderLimits` as `render_limits`.

::: vfs.rendering
