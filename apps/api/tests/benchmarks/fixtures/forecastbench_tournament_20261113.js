
        window.initLeaderboard_tournament = function()
        {
            const data = [{'Rank': 1, 'Team': 'anonymous_24.svg', 'Model Organization': 'Anonymous 24', 'Model': 'model-4', 'Dataset': 67.7, 'N dataset': 485, 'Dataset 95% CI': '[65.2, 70.4]', 'Market': 71.5, 'N market': 114, 'Market 95% CI': '[70.4, 72.7]', 'Overall': 69.5, 'N': 599, 'Overall 95% CI': '[68.1, 71.1]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.89', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Anonymous 24', 'Model Organization Logo': 'anonymous_24.svg'}, {'Rank': 2, 'Team': 'anonymous_24.svg', 'Model Organization': 'Anonymous 24', 'Model': 'model-5', 'Dataset': 66.4, 'N dataset': 485, 'Dataset 95% CI': '[63.5, 69.7]', 'Market': 71.3, 'N market': 114, 'Market 95% CI': '[70.3, 72.4]', 'Overall': 68.8, 'N': 599, 'Overall 95% CI': '[67.1, 70.5]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.69', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Anonymous 24', 'Model Organization Logo': 'anonymous_24.svg'}, {'Rank': 3, 'Team': 'deepmind.svg', 'Model Organization': 'Google DeepMind', 'Model': 'fire hedgehog', 'Dataset': 65.1, 'N dataset': 723, 'Dataset 95% CI': '[63.8, 66.5]', 'Market': 72.5, 'N market': 140, 'Market 95% CI': '[70.4, 75.0]', 'Overall': 68.6, 'N': 863, 'Overall 95% CI': '[67.4, 69.9]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.65', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Google DeepMind', 'Model Organization Logo': 'deepmind.svg'}, {'Rank': 4, 'Team': 'neurofusion.svg', 'Model Organization': 'NeuroFusion', 'Model': 'ensemble 1', 'Dataset': 65.8, 'N dataset': 485, 'Dataset 95% CI': '[63.7, 68.2]', 'Market': 71.3, 'N market': 114, 'Market 95% CI': '[70.3, 72.4]', 'Overall': 68.5, 'N': 599, 'Overall 95% CI': '[67.2, 69.8]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.60', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'NeuroFusion', 'Model Organization Logo': 'neurofusion.svg'}, {'Rank': 4, 'Team': 'neurofusion.svg', 'Model Organization': 'NeuroFusion', 'Model': 'ensemble 3', 'Dataset': 65.9, 'N dataset': 485, 'Dataset 95% CI': '[63.5, 68.6]', 'Market': 71.3, 'N market': 114, 'Market 95% CI': '[70.3, 72.4]', 'Overall': 68.5, 'N': 599, 'Overall 95% CI': '[67.1, 70.0]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.61', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'NeuroFusion', 'Model Organization Logo': 'neurofusion.svg'}, {'Rank': 6, 'Team': 'deepmind.svg', 'Model Organization': 'Google DeepMind', 'Model': 'blue croc', 'Dataset': 65.2, 'N dataset': 723, 'Dataset 95% CI': '[64.0, 66.5]', 'Market': 71.8, 'N market': 140, 'Market 95% CI': '[69.5, 74.0]', 'Overall': 68.3, 'N': 863, 'Overall 95% CI': '[67.0, 69.5]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.55', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Google DeepMind', 'Model Organization Logo': 'deepmind.svg'}, {'Rank': 6, 'Team': 'deepmind.svg', 'Model Organization': 'Google DeepMind', 'Model': 'ceramic-kettle', 'Dataset': 63.6, 'N dataset': 723, 'Dataset 95% CI': '[62.2, 65.0]', 'Market': 74.0, 'N market': 140, 'Market 95% CI': '[70.2, 78.2]', 'Overall': 68.3, 'N': 863, 'Overall 95% CI': '[66.6, 70.2]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.54', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Google DeepMind', 'Model Organization Logo': 'deepmind.svg'}, {'Rank': 8, 'Team': 'fri.svg', 'Model Organization': 'ForecastBench', 'Model': 'Superforecaster median forecast', 'Dataset': 63.5, 'N dataset': 521, 'Dataset 95% CI': '[62.3, 64.8]', 'Market': 73.8, 'N market': 57, 'Market 95% CI': '[70.9, 77.7]', 'Overall': 68.2, 'N': 578, 'Overall 95% CI': '[66.8, 69.8]', 'Supers > Forecaster?': '—', 'p-val Supers > Forecaster?': '—', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'ForecastBench', 'Model Organization Logo': 'fri.svg'}, {'Rank': 9, 'Team': 'torchcastai.svg', 'Model Organization': 'Torchcast AI', 'Model': 'captain-jack', 'Dataset': 64.5, 'N dataset': 723, 'Dataset 95% CI': '[63.3, 65.7]', 'Market': 72.1, 'N market': 140, 'Market 95% CI': '[69.1, 75.0]', 'Overall': 68.1, 'N': 863, 'Overall 95% CI': '[66.6, 69.5]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.44', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Torchcast AI', 'Model Organization Logo': 'torchcastai.svg'}, {'Rank': 9, 'Team': 'anonymous_22.svg', 'Model Organization': 'Anonymous 22', 'Model': 'ant-batch', 'Dataset': 65.7, 'N dataset': 485, 'Dataset 95% CI': '[63.9, 67.5]', 'Market': 70.8, 'N market': 114, 'Market 95% CI': '[69.0, 72.9]', 'Overall': 68.1, 'N': 599, 'Overall 95% CI': '[66.8, 69.5]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.49', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Anonymous 22', 'Model Organization Logo': 'anonymous_22.svg'}, {'Rank': 9, 'Team': 'anonymous_24.svg', 'Model Organization': 'Anonymous 24', 'Model': 'model-6', 'Dataset': 65.0, 'N dataset': 485, 'Dataset 95% CI': '[63.2, 67.0]', 'Market': 71.5, 'N market': 114, 'Market 95% CI': '[70.4, 72.7]', 'Overall': 68.1, 'N': 599, 'Overall 95% CI': '[67.0, 69.3]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.45', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Anonymous 24', 'Model Organization Logo': 'anonymous_24.svg'}, {'Rank': 12, 'Team': 'deepmind.svg', 'Model Organization': 'Google DeepMind', 'Model': 'big green leaf', 'Dataset': 65.1, 'N dataset': 723, 'Dataset 95% CI': '[63.9, 66.4]', 'Market': 71.2, 'N market': 140, 'Market 95% CI': '[68.8, 73.3]', 'Overall': 68.0, 'N': 863, 'Overall 95% CI': '[66.7, 69.2]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.42', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Google DeepMind', 'Model Organization Logo': 'deepmind.svg'}, {'Rank': 12, 'Team': 'torchcastai.svg', 'Model Organization': 'Torchcast AI', 'Model': 'rice-demon', 'Dataset': 64.7, 'N dataset': 723, 'Dataset 95% CI': '[63.6, 66.0]', 'Market': 71.7, 'N market': 140, 'Market 95% CI': '[68.6, 74.7]', 'Overall': 68.0, 'N': 863, 'Overall 95% CI': '[66.5, 69.4]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.43', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Torchcast AI', 'Model Organization Logo': 'torchcastai.svg'}, {'Rank': 14, 'Team': 'torchcastai.svg', 'Model Organization': 'Torchcast AI', 'Model': 'dragon-brother', 'Dataset': 64.4, 'N dataset': 723, 'Dataset 95% CI': '[63.3, 65.6]', 'Market': 71.8, 'N market': 140, 'Market 95% CI': '[68.9, 74.6]', 'Overall': 67.9, 'N': 863, 'Overall 95% CI': '[66.5, 69.2]', 'Supers > Forecaster?': 'No', 'p-val Supers > Forecaster?': '0.39', 'Forecaster > Public?': 'Yes', 'p-val Forecaster > Public?': '<0.001', 'Team Name': 'Torchcast AI', 'Model Organization Logo': 'torchcastai.svg'}, {'Rank': 504, 'Team': 'fri.svg', 'Model Organization': 'ForecastBench', 'Model': 'Always 0', 'Dataset': 37.8, 'N dataset': 39198, 'Dataset 95% CI': '[37.4, 38.1]', 'Market': 49.5, 'N market': 4105, 'Market 95% CI': '[48.3, 50.7]', 'Overall': 43.3, 'N': 43303, 'Overall 95% CI': '[42.7, 43.9]', 'Supers > Forecaster?': 'Yes', 'p-val Supers > Forecaster?': '<0.001', 'Forecaster > Public?': 'No', 'p-val Forecaster > Public?': '1.00', 'Team Name': 'ForecastBench', 'Model Organization Logo': 'fri.svg'}, {'Rank': 505, 'Team': 'fri.svg', 'Model Organization': 'ForecastBench', 'Model': 'Random Uniform', 'Dataset': 42.1, 'N dataset': 39198, 'Dataset 95% CI': '[41.8, 42.3]', 'Market': 42.1, 'N market': 4105, 'Market 95% CI': '[41.3, 42.9]', 'Overall': 42.1, 'N': 43303, 'Overall 95% CI': '[41.7, 42.5]', 'Supers > Forecaster?': 'Yes', 'p-val Supers > Forecaster?': '<0.001', 'Forecaster > Public?': 'No', 'p-val Forecaster > Public?': '1.00', 'Team Name': 'ForecastBench', 'Model Organization Logo': 'fri.svg'}, {'Rank': 506, 'Team': 'fri.svg', 'Model Organization': 'ForecastBench', 'Model': 'Always 1', 'Dataset': 21.7, 'N dataset': 39198, 'Dataset 95% CI': '[21.5, 22.0]', 'Market': 13.7, 'N market': 4105, 'Market 95% CI': '[13.0, 14.4]', 'Overall': 17.6, 'N': 43303, 'Overall 95% CI': '[17.2, 18.0]', 'Supers > Forecaster?': 'Yes', 'p-val Supers > Forecaster?': '<0.001', 'Forecaster > Public?': 'No', 'p-val Forecaster > Public?': '1.00', 'Team Name': 'ForecastBench', 'Model Organization Logo': 'fri.svg'}];
            const isTournament = true;
            const cols = ["Rank",  "Team",
                          "Model Organization", "Model Organization Logo", "Model",
                          "Dataset", "N dataset", "Dataset 95% CI",
                          "Market", "N market", "Market 95% CI",
                          "Overall", "N", "Overall 95% CI",
                          "Supers > Forecaster?", "p-val Supers > Forecaster?",
                          "Forecaster > Public?", "p-val Forecaster > Public?"];
            const teamColIndex = cols.indexOf("Team");
            const escapeTooltip = (text) =>
              String(text ?? '')
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            const columns = cols.map(name => {
                const col = { data: name, title: name };
                if (name === "Rank") {
                  col.className = 'dt-center';
                }
                if (name === "Team") {
                  col.className = 'dt-center';
                  col.render = (d, t, row) => {
                      if (t !== 'display') return row['Team Name'] || d;
                      if (!d) return '';
                      const tooltip = escapeTooltip(row['Team Name'] || d);
                      return `<span class="cell-tooltip" data-tooltip="${tooltip}"
                                    style="cursor:help; display:inline-flex;
                                    align-items:center;">` +
                             `<img src="/assets/images/org_logos/${d}" alt="${tooltip}"
                                   style="height:20px">` +
                             `</span>`;
                  };
                }

                if (name === "Model Organization") {
                  col.title = "Org";
                  col.className = 'dt-center';
                  col.render = (d, t, row) => {
                    if (t === 'display') {
                      const tooltip = escapeTooltip(d);
                      if (row['Model Organization Logo']) {
                        return `<span class="cell-tooltip" data-tooltip="${tooltip}"
                                      style="cursor:help; display:inline-flex;
                                      align-items:center;">` +
                               `<img src="/assets/images/org_logos/${row['Model Organization Logo']}"
                                alt="${tooltip}" style="height:20px">` +
                               `</span>`;
                      }
                      return `<span class="cell-tooltip" data-tooltip="${tooltip}"
                                    style="cursor:help">${d}</span>`;
                    }
                    return d; // Use text value for search/sort
                  };
                }

                if (["N dataset", "N market", "N", "Model Organization Logo",
                     "p-val Supers > Forecaster?", "p-val Forecaster > Public?"].includes(name)) {
                  col.visible = false;
                }

                if (name === "Dataset") {
                  col.title = "Dataset (N)";
                  col.render = (d, t, row) =>
                    t === "display"
                      ? parseFloat(d).toFixed(1) +
                        ' <span class="n-count">(' +
                        Number(row["N dataset"]).toLocaleString() +
                        ")</span>"
                      : d;
                  col.orderSequence = ["desc", "asc"];
                }

                if (name === "Market") {
                  col.title = "Market (N)";
                  col.render = (d, t, row) =>
                    t === "display"
                      ? parseFloat(d).toFixed(1) +
                        ' <span class="n-count">(' +
                        Number(row["N market"]).toLocaleString() +
                        ")</span>"
                      : d;
                  col.orderSequence = ["desc", "asc"];
                }

                if (name === "Overall") {
                  col.title = "Overall (N)";
                  col.render = (d, t, row) =>
                    t === "display"
                      ? parseFloat(d).toFixed(1) +
                        ' <span class="n-count">(' +
                        Number(row["N"]).toLocaleString() +
                        ")</span>"
                      : d;
                  col.orderSequence = ["desc", "asc"];
                }

                if (name === "Supers > Forecaster?"
                    || name === "Forecaster > Public?") {
                      col.orderable = false;
                }

                // Add cell tooltips that show the hidden p-values
                // Supers > Forecaster?
                if (name === "Supers > Forecaster?") {
                  col.className = (col.className ? col.className + ' ' : '') + 'dt-center';
                  col.render = (d, t, row) => {
                    if (t !== 'display') return d;
                    const p = row['p-val Supers > Forecaster?'];
                    const tip = (p == null || p === '') ? 'p-value unavailable' : 'p-val: ' + String(p);
                    const val = (d ?? '') === '' ? '' : d;
                    return `<span class="cell-tooltip" data-tooltip="${tip}"
                                  style="cursor:help">${val}</span>`;
                  };
                }

                // Forecaster > Public?
                if (name === "Forecaster > Public?") {
                  col.className = (col.className ? col.className + ' ' : '') + 'dt-center';
                  col.render = (d, t, row) => {
                    if (t !== 'display') return d;
                    const p = row['p-val Forecaster > Public?'];
                    const tip = (p == null || p === '') ? 'p-value unavailable' : 'p-val: ' + String(p);
                    const val = (d ?? '') === '' ? '' : d;
                    return `<span class="cell-tooltip" data-tooltip="${tip}"
                                  style="cursor:help">${val}</span>`;
                  };
                }

                if (["Dataset 95% CI", "Market 95% CI", "Overall 95% CI"].includes(name)) {
                  col.orderable = false;
                }

                return col;
            });

            // Register anonymous-team filter before DataTable init so it applies on first draw
            if (isTournament && teamColIndex >= 0) {
              $.fn.dataTable.ext.search.push(function(settings, data, dataIndex, rowData) {
                if (settings.nTable.id !== 'lb') return true;
                const showAnon = document.getElementById('show-anonymous')?.checked;
                if (showAnon) return true;
                const teamName =
                  (rowData && rowData["Team Name"]) ||
                  (settings.aoData?.[dataIndex]?._aData?.["Team Name"]) ||
                  '';
                return !(typeof teamName === 'string' &&
                         teamName.toLowerCase().trim().startsWith('anonymous'));
              });
            }

            $('#leaderboard-table-full').html(`
               ${isTournament ? `<div id="anon-toggle" style="margin-bottom:8px; display:flex;
                                      align-items:center; gap:6px;">
                   <input type="checkbox" id="show-anonymous" aria-label="Show anonymous teams">
                   <label for="show-anonymous" style="margin:0; cursor:pointer;">Show anonymous teams</label>
                 </div>` : ''}
               <table id="lb" class="display compact hover" style="width:100%">
               <thead>
                 <tr>
                   <th>Rank</th>
                   
                   <th class="column-header-tooltip" data-tooltip="Team">Team</th>
                   
                   <th class="column-header-tooltip" data-tooltip="Org">Org</th>
                   <th><!-- Model Organization Logo --></th>
                   <th class="column-header-tooltip" data-tooltip="Model">Model</th>
                   <th class="column-header-tooltip"
                       data-tooltip="Dataset (N)">Dataset (N)</th>
                   <th><!-- N dataset --></th>
                   <th class="column-header-tooltip" data-tooltip="Dataset 95% CI">Dataset 95% CI</th>
                   <th class="column-header-tooltip"
                       data-tooltip="Market (N)">Market (N)</th>
                   <th><!-- N market --></th>
                   <th class="column-header-tooltip" data-tooltip="Market 95% CI">Market 95% CI</th>
                   <th class="column-header-tooltip"
                       data-tooltip="Overall (N)">Overall (N)</th>
                   <th><!-- N --></th>
                   <th class="column-header-tooltip" data-tooltip="Overall 95% CI">Overall 95% CI</th>
                   <th class="column-header-tooltip"
                       data-tooltip="Supers > Forecaster?">Supers > Forecaster?</th>
                   <th><!-- p-val Supers > Forecaster? --></th>
                   <th class="column-header-tooltip"
                       data-tooltip="Forecaster > Public?">Forecaster > Public?</th>
                   <th><!-- p-val Forecaster > Public? --></th>
                 </tr>
               </thead>
               <tbody></tbody>
             </table>
             `);
             const table = $("#lb").DataTable({
               data: data,
               columns: columns,
               order: [[cols.indexOf("Overall"), "desc"]],
               pageLength:25,
               lengthMenu:[[10,25,50,100,-1],[10,25,50,100,"All"]],
               paging: true,
               info: true,
               dom:'<"top"lfr>t<"bottom"<"info-pagination-wrapper"ip>>',
               responsive: true,
               search: { regex: true, smart: true },
               createdRow: function(row, data, dataIndex) {
                 if (["Superforecaster median forecast", "Public median forecast"].includes(data.Model)) {
                   $(row).css('background-color', '#fef0e6');
                 }
               },
               infoCallback: function(settings, start, end, max, total, pre) {
                   return pre + '<br>last updated 2026-11-11';
               }
           });

           if (isTournament && teamColIndex >= 0) {
             $('#show-anonymous').on('change', function() { table.draw(); });
             // Apply the filter once on load so anonymous rows start hidden
             table.draw();
           }
            table.on('draw.dt', function () {
              initializeTooltips();
            });
           window.tooltipContent = {
             'Team': `The team that submitted forecasts.`,
             'Org': `The organization that developed the model.`,
             'Model': `The name of the model that was used to generate the forecasts.`,
             'Dataset (N)': `Brier Index (%) on dataset questions. Scale: 100 = perfect, 50 = always predicting 50%, 0 = maximally wrong. Higher scores are better.`,
             'Dataset 95% CI': `Bootstrapped 95% confidence interval for the Dataset Brier Index (%).`,
             'Market (N)': `Brier Index (%) on market questions. Scale: 100 = perfect, 50 = always predicting 50%, 0 = maximally wrong. Higher scores are better.`,
             'Market 95% CI': `Bootstrapped 95% confidence interval for the Market Brier Index (%).`,
             'Overall (N)': `Brier Index (%) across all questions. Scale: 100 = perfect, 50 = always predicting 50%, 0 = maximally wrong. Higher scores are better.`,
             'Overall 95% CI': `Bootstrapped 95% confidence interval for the Overall Brier Index (%).`,
             'Supers > Forecaster?': `One-sided p-value comparing each forecaster to the superforecaster median based on 1,999 simulations, with<br>H₀: This forecaster performs at least as well as the superforecaster median.<br>H₁: The superforecaster median outperforms this forecaster.`,
             'Forecaster > Public?': `One-sided p-value comparing each forecaster to the public median based on 1,999 simulations, with<br>H₀: The public median performs at least as well as this forecaster.<br>H₁: This forecaster outperforms the public median.`
           };
           initializeTooltips();
        };