---- MODULE TaskBoardCoordination ----
(*
Formal specification of dharma_swarm task board coordination.

Models the distributed task claiming, execution, and completion protocol
to verify safety and liveness properties.

Based on AWS TLA+ patterns for distributed systems.
*)

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
    Agents,         \* Set of agent IDs
    Tasks,          \* Set of task IDs
    MaxConcurrent,  \* Maximum concurrent tasks per agent
    NULL,           \* Null value for unassigned tasks
    Results         \* Finite set of possible results (for model checking)

VARIABLES
    task_status,    \* Tasks -> {"pending", "claimed", "running", "completed", "failed"}
    task_owner,     \* Tasks -> Agent \cup {NULL}
    task_result,    \* Tasks -> Result \cup {NULL}
    agent_state,    \* Agents -> {"idle", "working", "failed"}
    agent_tasks,    \* Agents -> Sequence of task IDs (active tasks)
    message_queue   \* Sequence of messages between agents

----

(*
Type invariant - ensures all variables stay in valid states.
*)
TypeOK ==
    /\ task_status \in [Tasks -> {"pending", "claimed", "running", "completed", "failed"}]
    /\ task_owner \in [Tasks -> Agents \cup {NULL}]
    /\ task_result \in [Tasks -> Results \cup {NULL}]
    /\ agent_state \in [Agents -> {"idle", "working", "failed"}]
    /\ agent_tasks \in [Agents -> Seq(Tasks)]
    /\ message_queue \in Seq([type: Results, from: Agents, to: Agents, task: Tasks])

(*
Initial state - all tasks pending, all agents idle.
*)
Init ==
    /\ task_status = [t \in Tasks |-> "pending"]
    /\ task_owner = [t \in Tasks |-> NULL]
    /\ task_result = [t \in Tasks |-> NULL]
    /\ agent_state = [a \in Agents |-> "idle"]
    /\ agent_tasks = [a \in Agents |-> << >>]
    /\ message_queue = << >>

----

(*
Agent claims a pending task.

Preconditions:
- Task must be pending
- Agent must have capacity (< MaxConcurrent tasks)
- Agent must not have failed

Postconditions:
- Task status becomes "claimed"
- Task is owned by the agent
- Agent's task list includes the task
*)
ClaimTask(agent, task) ==
    /\ task_status[task] = "pending"
    /\ Len(agent_tasks[agent]) < MaxConcurrent
    /\ agent_state[agent] # "failed"
    /\ task_status' = [task_status EXCEPT ![task] = "claimed"]
    /\ task_owner' = [task_owner EXCEPT ![task] = agent]
    /\ agent_tasks' = [agent_tasks EXCEPT ![agent] = Append(@, task)]
    /\ UNCHANGED <<task_result, agent_state, message_queue>>

(*
Agent starts executing a claimed task.
*)
StartTask(agent, task) ==
    /\ task_status[task] = "claimed"
    /\ task_owner[task] = agent
    /\ task_status' = [task_status EXCEPT ![task] = "running"]
    /\ agent_state' = [agent_state EXCEPT ![agent] = "working"]
    /\ UNCHANGED <<task_owner, task_result, agent_tasks, message_queue>>

(*
Agent completes a task successfully.

Postconditions:
- Task status becomes "completed"
- Task has a result
- Task is removed from agent's active list
- Agent becomes idle if no other tasks
*)
CompleteTask(agent, task, result) ==
    /\ task_status[task] = "running"
    /\ task_owner[task] = agent
    /\ task_status' = [task_status EXCEPT ![task] = "completed"]
    /\ task_result' = [task_result EXCEPT ![task] = result]
    /\ LET remaining_tasks == SelectSeq(agent_tasks[agent], LAMBDA t: t # task)
       IN /\ agent_tasks' = [agent_tasks EXCEPT ![agent] = remaining_tasks]
          /\ agent_state' = [agent_state EXCEPT ![agent] =
                IF Len(remaining_tasks) = 0 THEN "idle" ELSE "working"]
    /\ UNCHANGED <<task_owner, message_queue>>

(*
Task fails during execution.

Postconditions:
- Task status becomes "failed"
- Task is removed from agent's list
- Agent continues (doesn't fail unless all tasks fail)
*)
FailTask(agent, task, reason) ==
    /\ task_status[task] \in {"claimed", "running"}
    /\ task_owner[task] = agent
    /\ task_status' = [task_status EXCEPT ![task] = "failed"]
    /\ task_result' = [task_result EXCEPT ![task] = reason]
    /\ LET remaining_tasks == SelectSeq(agent_tasks[agent], LAMBDA t: t # task)
       IN /\ agent_tasks' = [agent_tasks EXCEPT ![agent] = remaining_tasks]
          /\ agent_state' = [agent_state EXCEPT ![agent] =
                IF Len(remaining_tasks) = 0 THEN "idle" ELSE "working"]
    /\ UNCHANGED <<task_owner, message_queue>>

(*
Agent fails completely (loses all claimed tasks).
*)
AgentFail(agent) ==
    /\ agent_state[agent] # "failed"
    /\ agent_state' = [agent_state EXCEPT ![agent] = "failed"]
    /\ LET agent_claimed_tasks == {t \in Tasks : task_owner[t] = agent}
       IN /\ task_status' = [t \in Tasks |->
                IF t \in agent_claimed_tasks /\ task_status[t] # "completed"
                THEN "pending"  \* Release back to pending
                ELSE task_status[t]]
          /\ task_owner' = [t \in Tasks |->
                IF t \in agent_claimed_tasks /\ task_status[t] # "completed"
                THEN NULL
                ELSE task_owner[t]]
    /\ agent_tasks' = [agent_tasks EXCEPT ![agent] = << >>]
    /\ UNCHANGED <<task_result, message_queue>>

----

(*
All possible next states.
*)
Next ==
    \/ \E a \in Agents, t \in Tasks : ClaimTask(a, t)
    \/ \E a \in Agents, t \in Tasks : StartTask(a, t)
    \/ \E a \in Agents, t \in Tasks, r \in Results : CompleteTask(a, t, r)
    \/ \E a \in Agents, t \in Tasks, r \in Results : FailTask(a, t, r)
    \/ \E a \in Agents : AgentFail(a)

----
(*
=============================================================================
SAFETY PROPERTIES (Invariants that must always hold)
=============================================================================
*)

(*
CRITICAL: Each task has exactly one owner (or NULL).

Since task_owner is a function Tasks -> (Agents \cup {NULL}),
this is guaranteed by the type system. We just verify that
claimed/running tasks have non-NULL owners.
*)
NoTaskDuplication ==
    TRUE  \* Trivially true by type system - task_owner is a function

(*
Every claimed/running task has an owner.
*)
ClaimedTasksHaveOwner ==
    \A t \in Tasks :
        task_status[t] \in {"claimed", "running"}
        => task_owner[t] # NULL

(*
Completed tasks have results.
*)
CompletedTasksHaveResults ==
    \A t \in Tasks :
        task_status[t] = "completed"
        => task_result[t] # NULL

(*
Agent capacity is never exceeded.
*)
AgentCapacityRespected ==
    \A a \in Agents :
        Len(agent_tasks[a]) <= MaxConcurrent

(*
Failed agents own no tasks.
*)
FailedAgentsHaveNoTasks ==
    \A a \in Agents :
        agent_state[a] = "failed"
        => Len(agent_tasks[a]) = 0

(*
Task ownership consistency: If agent owns task, task is in agent's list.
*)
OwnershipConsistency ==
    \A a \in Agents, t \in Tasks :
        (task_owner[t] = a /\ task_status[t] \in {"claimed", "running"})
        => \E i \in 1..Len(agent_tasks[a]) : agent_tasks[a][i] = t

----
(*
=============================================================================
LIVENESS PROPERTIES (Progress guarantees)
=============================================================================
*)

(*
Eventually, all pending tasks are either completed or failed
(assuming at least one non-failed agent exists).
*)
EventualCompletion ==
    (\E a \in Agents : agent_state[a] # "failed")
    =>
    \A t \in Tasks :
        task_status[t] = "pending"
        ~> task_status[t] \in {"completed", "failed"}

(*
If a task is claimed, it eventually reaches a terminal state.
*)
ClaimedTasksEventuallyComplete ==
    \A t \in Tasks :
        task_status[t] = "claimed"
        ~> task_status[t] \in {"completed", "failed"}

(*
If all agents fail, no task remains claimed.
*)
NoStuckTasks ==
    (\A a \in Agents : agent_state[a] = "failed")
    =>
    (\A t \in Tasks : task_status[t] \in {"pending", "completed", "failed"})

----
(*
=============================================================================
SPECIFICATION
=============================================================================
*)

(*
System specification with fairness constraints.

Weak fairness: If an action is continuously enabled, it will eventually happen.
Strong fairness: If an action is infinitely often enabled, it will eventually happen.
*)
Spec == Init /\ [][Next]_<<task_status, task_owner, task_result, agent_state, agent_tasks, message_queue>>
            /\ WF_<<task_status, task_owner, task_result, agent_state, agent_tasks, message_queue>>(Next)

====
