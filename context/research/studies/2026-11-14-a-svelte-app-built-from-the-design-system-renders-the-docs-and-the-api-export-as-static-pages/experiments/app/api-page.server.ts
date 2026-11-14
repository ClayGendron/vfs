import { render } from "#lib/docs.server";
import api from "#lib/api.json";

export const entries = () => api.names.map((name: string) => ({ name }));

export async function load({ params }) {
  const object = (api.objects as Record<string, any>)[params.name];
  const page = `reference/api/${params.name}`;
  return {
    name: params.name,
    kind: object.kind,
    signature: object.signature ?? null,
    doc: await render(object.doc, page),
    members: await Promise.all(
      (object.members ?? []).map(async (m: any) => ({ ...m, doc: await render(m.doc, page) })),
    ),
  };
}
