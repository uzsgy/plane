/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useState } from "react";
import { observer } from "mobx-react";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { EIssuesStoreType } from "@plane/types";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
import { csvDownload } from "@plane/utils";
import { useIssues } from "@/hooks/store/use-issues";
import { IssueService } from "@/services/issue/issue.service";

type Props = {
  workspaceSlug: string;
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
};

const issueService = new IssueService();

export const IssueCsvImportModal = observer(function IssueCsvImportModal(props: Props) {
  const { workspaceSlug, projectId, isOpen, onClose } = props;
  const { t } = useTranslation();
  const {
    issues: { fetchIssuesWithExistingPagination },
  } = useIssues(EIssuesStoreType.PROJECT);

  const [file, setFile] = useState<File | null>(null);
  const [isImporting, setIsImporting] = useState(false);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setFile(acceptedFiles[0] ?? null);
  }, []);

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: { "text/csv": [".csv"] },
    multiple: false,
  });

  const handleClose = () => {
    onClose();
    setTimeout(() => setFile(null), 300);
  };

  const handleDownloadSample = () => {
    csvDownload(
      [
        [
          "Name",
          "Description",
          "Priority",
          "State",
          "Labels",
          "Assignees",
          "Module",
          "Cycle",
          "Start Date",
          "Target Date",
        ],
        [
          "Fix login bug",
          "Users cannot login",
          "high",
          "Todo",
          "Bug",
          "user@example.com",
          "Sprint 1",
          "Cycle 1",
          "2026-01-01",
          "2026-01-15",
        ],
        [
          "Update docs",
          "Refresh onboarding guide",
          "medium",
          "In Progress",
          "Documentation",
          "",
          "",
          "",
          "2026-02-01",
          "2026-02-28",
        ],
      ],
      "work-items-import-sample"
    );
  };

  const handleImport = async () => {
    if (!file) return;

    setIsImporting(true);
    try {
      const result = await issueService.importIssuesFromCsv(workspaceSlug, projectId, file);

      await fetchIssuesWithExistingPagination(workspaceSlug, projectId, "mutation");

      if (result.created > 0) {
        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: t("project.issues_import.toast.success.title"),
          message: t("project.issues_import.toast.success.message", { count: result.created }),
        });
      }

      if (result.failed > 0) {
        setToast({
          type: TOAST_TYPE.ERROR,
          title: t("project.issues_import.toast.partial.title"),
          message: t("project.issues_import.toast.partial.message", {
            created: result.created,
            failed: result.failed,
          }),
        });
      }

      if (result.created === 0 && result.failed === 0) {
        setToast({
          type: TOAST_TYPE.ERROR,
          title: t("project.issues_import.toast.empty.title"),
          message: t("project.issues_import.toast.empty.message"),
        });
      }

      handleClose();
    } catch (error: any) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("project.issues_import.toast.failed.title"),
        message: error?.error ?? t("project.issues_import.toast.failed.message"),
      });
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <ModalCore isOpen={isOpen} handleClose={handleClose} position={EModalPosition.TOP} width={EModalWidth.LG}>
      <div className="p-5">
        <h3 className="text-18 font-medium text-primary">{t("project.issues_import.title")}</h3>
        <p className="mt-2 text-13 text-secondary">{t("project.issues_import.description")}</p>

        <button type="button" className="mt-3 text-13 font-medium text-accent-primary" onClick={handleDownloadSample}>
          {t("project.issues_import.download_sample")}
        </button>

        <div
          {...getRootProps()}
          className={`mt-4 cursor-pointer rounded-lg border border-dashed p-8 text-center ${
            isDragActive ? "border-accent-strong bg-surface-2" : "border-subtle"
          }`}
        >
          <input {...getInputProps()} />
          {file ? (
            <p className="text-13 text-primary">{file.name}</p>
          ) : (
            <p className="text-13 text-secondary">
              {isDragActive ? t("project.issues_import.dropzone.active") : t("project.issues_import.dropzone.inactive")}
            </p>
          )}
          <p className="mt-1 text-11 text-tertiary">{t("project.issues_import.dropzone.file_type")}</p>
        </div>

        {fileRejections.length > 0 && (
          <p className="mt-2 text-13 text-danger-primary">{t("project.issues_import.toast.invalid_file.message")}</p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={handleClose}>
            {t("project.issues_import.buttons.cancel")}
          </Button>
          <Button variant="primary" onClick={handleImport} disabled={!file} loading={isImporting}>
            {isImporting ? t("project.issues_import.progress.importing") : t("project.issues_import.buttons.import")}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
});
