-- vfs never creates the extension itself: CREATE EXTENSION needs rights an
-- application role does not have on a managed server, so the test cluster
-- installs it once here, on first start, and first touch only proves it.
CREATE EXTENSION IF NOT EXISTS vector;
