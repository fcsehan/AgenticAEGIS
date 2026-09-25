import { useEffect } from "react";
import { useBlocker } from "react-router-dom";
import { useEditorText } from "./useEditorText";

export function useUnsavedChanges(dirty: boolean) {
  const blocker = useBlocker(dirty);
  const tx = useEditorText();
  useEffect(() => {
    if (blocker.state === "blocked") {
      if (
        window.confirm(
          tx("Unsaved changes. Leave this page?"),
        )
      )
        blocker.proceed();
      else blocker.reset();
    }
  }, [blocker, tx]);
}
