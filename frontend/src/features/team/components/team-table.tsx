"use client";

import { useMemo, useState } from "react";
import { MoreHorizontal, UserPlus, Users } from "lucide-react";
import { toast } from "sonner";
import type { ColumnDef } from "@tanstack/react-table";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DataTable, DataTablePagination, DataTableToolbar } from "@/components/data-table";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { EmptyState } from "@/components/feedback/empty-state";
import { FilterDropdown, optionsFromEnum } from "@/components/shared/filter-dropdown";
import { PermissionGate } from "@/components/shared/permission-gate";
import { StatusBadge } from "@/components/shared/status-badge";
import { MEMBERSHIP_STATUSES } from "@/config/enums";
import { MEMBERSHIP_STATUS_LABELS, ROLE_SLUG_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { InviteMemberDialog } from "@/features/team/components/invite-member-dialog";
import { MemberRoleDialog } from "@/features/team/components/member-role-dialog";
import {
  useMembers,
  useRemoveMember,
  useUpdateMember,
} from "@/features/team/api/use-team";
import { useListState } from "@/hooks/use-list-state";
import { errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-provider";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { formatDateTime, initials, userDisplayName } from "@/lib/utils/format";
import type { Membership } from "@/types/api";

const FILTER_KEYS = ["status"] as const;

/** Workspace members (spec §33). */
export function TeamTable() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const list = useListState({ filterKeys: FILTER_KEYS, defaultSort: "created_at" });

  const [inviteOpen, setInviteOpen] = useState(false);
  const [editingRoles, setEditingRoles] = useState<Membership | null>(null);
  const [pendingRemove, setPendingRemove] = useState<Membership | null>(null);

  const query = useMembers({
    page: list.page,
    page_size: list.pageSize,
    status: list.filter("status"),
    sort: list.sort,
    order: list.order,
  });

  const updateMember = useUpdateMember();
  const removeMember = useRemoveMember();

  const columns = useMemo<ColumnDef<Membership, unknown>[]>(
    () => [
      {
        id: "user",
        meta: { label: "Member" },
        enableHiding: false,
        header: () => <span className="text-xs font-medium">Member</span>,
        cell: ({ row }) => {
          const name = userDisplayName(row.original.user);
          return (
            <div className="flex min-w-0 items-center gap-2.5">
              <Avatar className="size-7">
                <AvatarFallback>{initials(name, row.original.user?.email)}</AvatarFallback>
              </Avatar>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-medium">{name}</span>
                  {row.original.user_id === user?.id ? (
                    <Badge variant="secondary">You</Badge>
                  ) : null}
                  {row.original.is_owner ? <Badge variant="info">Owner</Badge> : null}
                </div>
                <div className="text-muted-foreground truncate text-xs">
                  {row.original.user?.email ?? "—"}
                </div>
              </div>
            </div>
          );
        },
      },
      {
        id: "roles",
        meta: { label: "Roles" },
        header: () => <span className="text-xs font-medium">Roles</span>,
        cell: ({ row }) => {
          const roles = row.original.roles ?? [];
          if (roles.length === 0) {
            return <span className="text-muted-foreground text-sm">No role</span>;
          }
          return (
            <div className="flex flex-wrap gap-1">
              {roles.map((slug) => (
                <Badge key={slug} variant="outline">
                  {ROLE_SLUG_LABELS[slug] ?? slug}
                </Badge>
              ))}
            </div>
          );
        },
      },
      {
        accessorKey: "status",
        meta: { label: "Status" },
        header: () => <span className="text-xs font-medium">Status</span>,
        cell: ({ row }) => (
          <StatusBadge status={row.original.status} labels={MEMBERSHIP_STATUS_LABELS} />
        ),
      },
      {
        id: "last_login",
        meta: { label: "Last login" },
        header: () => <span className="text-xs font-medium">Last login</span>,
        cell: ({ row }) => (
          <span className="tabular text-sm">
            {row.original.user?.last_login_at
              ? formatDateTime(row.original.user.last_login_at)
              : "Never"}
          </span>
        ),
      },
      {
        id: "actions",
        size: 48,
        enableHiding: false,
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => {
          const member = row.original;
          const canUpdate = can(PERM.USER_UPDATE);
          const canRemove = can(PERM.USER_DELETE);
          // The owner's membership and your own are protected here so the UI
          // never offers a change that would lock the workspace or the user out.
          const isSelf = member.user_id === user?.id;
          const protectedMember = member.is_owner || isSelf;

          if (!canUpdate && !canRemove) return null;

          return (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="Member actions">
                  <MoreHorizontal className="size-4" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                {canUpdate ? (
                  <DropdownMenuItem
                    onSelect={() => setEditingRoles(member)}
                    disabled={member.is_owner}
                  >
                    Edit roles
                  </DropdownMenuItem>
                ) : null}

                {canUpdate && !protectedMember && member.status === "ACTIVE" ? (
                  <DropdownMenuItem
                    onSelect={() => {
                      void updateMember
                        .mutateAsync({
                          membershipId: member.id,
                          payload: { status: "SUSPENDED" },
                        })
                        .then(() => toast.success("Member deactivated"))
                        .catch((error: unknown) =>
                          toast.error("Couldn't deactivate member", {
                            description: errorMessage(error),
                          }),
                        );
                    }}
                  >
                    Deactivate
                  </DropdownMenuItem>
                ) : null}

                {canUpdate && member.status === "SUSPENDED" ? (
                  <DropdownMenuItem
                    onSelect={() => {
                      void updateMember
                        .mutateAsync({
                          membershipId: member.id,
                          payload: { status: "ACTIVE" },
                        })
                        .then(() => toast.success("Member reactivated"))
                        .catch((error: unknown) =>
                          toast.error("Couldn't reactivate member", {
                            description: errorMessage(error),
                          }),
                        );
                    }}
                  >
                    Reactivate
                  </DropdownMenuItem>
                ) : null}

                {canRemove && !protectedMember ? (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      onSelect={() => setPendingRemove(member)}
                    >
                      Remove from workspace
                    </DropdownMenuItem>
                  </>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          );
        },
      },
    ],
    [can, updateMember, user?.id],
  );

  const meta = query.data?.meta;

  return (
    <>
      <DataTable
        columns={columns}
        data={query.data?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={query.isPending}
        isFetching={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        resourceLabel="your team"
        mobileRow={(row) => (
          <div className="space-y-1">
            <div className="flex items-start justify-between gap-2">
              <span className="font-medium">{userDisplayName(row.user)}</span>
              <StatusBadge status={row.status} labels={MEMBERSHIP_STATUS_LABELS} />
            </div>
            <div className="text-muted-foreground text-xs">{row.user?.email}</div>
            <div className="text-muted-foreground text-xs">
              {(row.roles ?? []).map((slug) => ROLE_SLUG_LABELS[slug] ?? slug).join(", ") ||
                "No role"}
            </div>
          </div>
        )}
        toolbar={(table) => (
          <DataTableToolbar
            table={table}
            activeFilterCount={list.activeFilterCount}
            onResetFilters={list.resetFilters}
            filters={
              <FilterDropdown
                label="Status"
                options={optionsFromEnum(MEMBERSHIP_STATUSES, MEMBERSHIP_STATUS_LABELS)}
                value={list.filter("status")}
                onChange={(value) => list.setFilter("status", value)}
              />
            }
          />
        )}
        emptyState={
          <EmptyState
            icon={Users}
            title="No members yet"
            description="Add teammates so they can discover publishers, review opportunities and approve submissions."
            action={
              <PermissionGate permission={PERM.USER_CREATE}>
                <Button size="sm" onClick={() => setInviteOpen(true)}>
                  <UserPlus className="size-4" aria-hidden />
                  Add member
                </Button>
              </PermissionGate>
            }
          />
        }
        footer={() =>
          meta ? (
            <DataTablePagination
              meta={meta}
              onPageChange={list.setPage}
              onPageSizeChange={list.setPageSize}
            />
          ) : null
        }
      />

      <InviteMemberDialog open={inviteOpen} onOpenChange={setInviteOpen} />

      <MemberRoleDialog
        member={editingRoles}
        onOpenChange={(open) => !open && setEditingRoles(null)}
      />

      <ConfirmDialog
        open={pendingRemove !== null}
        onOpenChange={(open) => !open && setPendingRemove(null)}
        title="Remove this member?"
        description={
          <>
            <strong>{userDisplayName(pendingRemove?.user)}</strong> will lose access to this
            workspace immediately. Their account and any other workspaces are unaffected.
          </>
        }
        confirmLabel="Remove member"
        destructive
        onConfirm={async () => {
          if (!pendingRemove) return;
          try {
            await removeMember.mutateAsync(pendingRemove.id);
            toast.success("Member removed");
            setPendingRemove(null);
          } catch (error) {
            toast.error("Couldn't remove member", { description: errorMessage(error) });
            throw error;
          }
        }}
      />
    </>
  );
}
