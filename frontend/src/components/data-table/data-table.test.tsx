import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ColumnDef } from "@tanstack/react-table";

import { DataTable, DataTablePagination } from "@/components/data-table";
import { EmptyState } from "@/components/feedback/empty-state";
import { ApiError } from "@/lib/api/errors";
import { makeMeta } from "@/test/utils";

interface Row {
  id: string;
  name: string;
  score: number;
}

const rows: Row[] = [
  { id: "1", name: "Directory One", score: 82 },
  { id: "2", name: "Directory Two", score: 41 },
];

const columns: ColumnDef<Row, unknown>[] = [
  {
    accessorKey: "name",
    meta: { label: "Name" },
    header: () => <span>Name</span>,
    cell: ({ row }) => <span>{row.original.name}</span>,
  },
  {
    accessorKey: "score",
    meta: { label: "Score" },
    header: () => <span>Score</span>,
    cell: ({ row }) => <span>{row.original.score}</span>,
  },
];

describe("DataTable", () => {
  it("renders rows", () => {
    render(<DataTable columns={columns} data={rows} getRowId={(row) => row.id} />);

    expect(screen.getByText("Directory One")).toBeInTheDocument();
    expect(screen.getByText("Directory Two")).toBeInTheDocument();
  });

  it("shows a skeleton instead of a blank screen while loading", () => {
    const { container } = render(
      <DataTable columns={columns} data={[]} getRowId={(row) => row.id} isLoading />,
    );

    expect(screen.queryByText("Directory One")).not.toBeInTheDocument();
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it("renders the error state with a retry action, and offers no retry for a 403", async () => {
    const onRetry = vi.fn();

    const { unmount } = render(
      <DataTable
        columns={columns}
        data={[]}
        getRowId={(row) => row.id}
        error={new ApiError({ status: 500, code: "INTERNAL_ERROR", message: "Boom" })}
        onRetry={onRetry}
        resourceLabel="your publishers"
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    unmount();

    render(
      <DataTable
        columns={columns}
        data={[]}
        getRowId={(row) => row.id}
        error={
          new ApiError({ status: 403, code: "PERMISSION_DENIED", message: "Denied" })
        }
        onRetry={onRetry}
      />,
    );

    // Retrying a 403 cannot help, so no retry button is offered.
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
    expect(screen.getByText("You don't have access")).toBeInTheDocument();
  });

  it("renders the supplied empty state when there are no rows", () => {
    render(
      <DataTable
        columns={columns}
        data={[]}
        getRowId={(row) => row.id}
        emptyState={<EmptyState title="No publishers yet" description="Run discovery." />}
      />,
    );

    expect(screen.getByText("No publishers yet")).toBeInTheDocument();
    expect(screen.getByText("Run discovery.")).toBeInTheDocument();
  });

  it("reports the clicked row", async () => {
    const onRowClick = vi.fn();

    render(
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        onRowClick={onRowClick}
      />,
    );

    await userEvent.click(screen.getByText("Directory Two"));
    expect(onRowClick).toHaveBeenCalledWith(rows[1]);
  });

  it("keeps rows visible during a background refetch rather than replacing them", () => {
    render(
      <DataTable columns={columns} data={rows} getRowId={(row) => row.id} isFetching />,
    );

    expect(screen.getByText("Directory One")).toBeInTheDocument();
  });
});

describe("DataTablePagination", () => {
  it("reports the visible range and disables the edges", () => {
    render(
      <DataTablePagination
        meta={makeMeta({ page: 1, page_size: 25, total: 60, total_pages: 3, has_next: true })}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );

    expect(screen.getByText("1–25 of 60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next page" })).toBeEnabled();
  });

  it("navigates pages", async () => {
    const onPageChange = vi.fn();

    render(
      <DataTablePagination
        meta={makeMeta({
          page: 2,
          page_size: 25,
          total: 60,
          total_pages: 3,
          has_next: true,
          has_previous: true,
        })}
        onPageChange={onPageChange}
        onPageSizeChange={() => {}}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(onPageChange).toHaveBeenCalledWith(3);

    await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(onPageChange).toHaveBeenCalledWith(1);

    await userEvent.click(screen.getByRole("button", { name: "Last page" }));
    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it("says 'No results' rather than showing a 0–0 range", () => {
    render(
      <DataTablePagination
        meta={makeMeta({ total: 0, total_pages: 0 })}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );

    expect(screen.getByText("No results")).toBeInTheDocument();
  });
});
