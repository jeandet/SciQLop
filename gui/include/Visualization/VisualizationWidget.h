#ifndef SCIQLOP_VISUALIZATIONWIDGET_H
#define SCIQLOP_VISUALIZATIONWIDGET_H

#include "Visualization/IVisualizationWidget.h"

#include <QLoggingCategory>
#include <QWidget>

Q_DECLARE_LOGGING_CATEGORY(LOG_VisualizationWidget)

class QMenu;
class Variable;
class VisualizationTabWidget;

namespace Ui {
class VisualizationWidget;
} // namespace Ui

class VisualizationWidget : public QWidget, public IVisualizationWidget {
    Q_OBJECT

public:
    explicit VisualizationWidget(QWidget *parent = 0);
    virtual ~VisualizationWidget();

    // IVisualizationWidget interface
    void accept(IVisualizationWidgetVisitor *visitor) override;
    bool canDrop(const Variable &variable) const override;
    QString name() const override;

public slots:
    /**
     * Attaches to a menu the menu relating to the visualization of a variable
     * @param menu the parent menu of the generated menu
     * @param variable the variable for which to generate the menu
     */
    void attachVariableMenu(QMenu *menu, std::shared_ptr<Variable> variable) noexcept;

private:
    Ui::VisualizationWidget *ui;
};

#endif // VISUALIZATIONWIDGET_H
