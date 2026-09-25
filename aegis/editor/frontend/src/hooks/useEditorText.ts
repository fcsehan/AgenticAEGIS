import { useCallback } from "react";
import { useTranslation } from "react-i18next";
/** English source keys share one catalog across the authoring UI. */
export function useEditorText() {
  const { t } = useTranslation("editor");
  return useCallback(
    (source: string) =>
      t(source, { keySeparator: false, defaultValue: source }),
    [t],
  );
}
